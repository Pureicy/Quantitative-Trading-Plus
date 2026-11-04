from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from inspect import Parameter, signature
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from local_store import LocalStore

try:
    import akshare as ak
except ImportError:
    ak = None


DEFAULT_TOP_N = 30
DEFAULT_MAX_PRICE = 130.0
DEFAULT_MIN_EXPECTED_MARKET_ROWS = 100
FOCUS_SCORE_THRESHOLD = 120.0
NEAR_COST_PCT_THRESHOLD = 2.0
LOSS_WATCH_PCT_THRESHOLD = -5.0

REDEEM_KEYWORDS = ("已公告强赎", "公告要强赎", "强赎实施", "临近到期")
EXCLUDED_NAME_KEYWORDS = ("退债",)
EXCLUDED_SPOT_KEYWORDS = ("定转",)

COL_BOND_CODE = "债券代码"
COL_BOND_NAME = "债券简称"
COL_BOND_PRICE = "债现价"
COL_BOND_PREMIUM = "转股溢价率"

HELD_GROUP = "持仓观察"
UNHELD_GROUP = "新机会"
PROFIT_STATUS = "浮盈"
LOSS_STATUS = "浮亏"
FLAT_STATUS = "持平"
NEAR_COST_SIGNAL = "接近成本"
FOCUS_SIGNAL = "重点机会"
LOSS_SIGNAL = "浮亏关注"


@dataclass(frozen=True)
class ScanProgress:
    stage: str
    label: str
    percent: int
    detail: str = ""
    metrics: dict | None = None


def _emit_scan_progress(
    callback: Callable[[ScanProgress], None] | None,
    stage: str,
    label: str,
    percent: int,
    detail: str = "",
    metrics: dict | None = None,
) -> None:
    if callback is None:
        return
    try:
        callback(
            ScanProgress(
                stage=stage,
                label=label,
                percent=max(0, min(int(percent), 100)),
                detail=detail,
                metrics=metrics,
            )
        )
    except Exception:
        # A UI progress sink must never make the market scan fail.
        pass


def _call_with_optional_progress(method, *, progress_callback):
    try:
        parameters = signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "progress_callback" in parameters or any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return method(progress_callback=progress_callback)
    return method()


def build_snapshot_review(current_snapshot: dict, previous_snapshot: dict | None) -> dict:
    current_time = str(current_snapshot.get("scan_time", ""))
    previous_time = str((previous_snapshot or {}).get("scan_time", ""))

    if not previous_snapshot:
        return {
            "current_scan_time": current_time,
            "previous_scan_time": previous_time,
            "new_count": 0,
            "dropped_count": 0,
            "changed_count": 0,
            "new_rows": [],
            "dropped_rows": [],
            "changed_rows": [],
            "summary": "首次生成快照，暂无上一期可供对比。",
        }

    current_rows = _snapshot_row_lookup(current_snapshot.get("rows", []))
    previous_rows = _snapshot_row_lookup(previous_snapshot.get("rows", []))

    new_codes = sorted(
        set(current_rows) - set(previous_rows),
        key=lambda code: (current_rows[code]["rank"], code),
    )
    dropped_codes = sorted(
        set(previous_rows) - set(current_rows),
        key=lambda code: (previous_rows[code]["rank"], code),
    )

    new_rows = [
        {
            "bond_code": code,
            "bond_name": current_rows[code]["bond_name"],
            "current_rank": current_rows[code]["rank"],
            "current_score": current_rows[code]["double_low_score"],
        }
        for code in new_codes
    ]
    dropped_rows = [
        {
            "bond_code": code,
            "bond_name": previous_rows[code]["bond_name"],
            "previous_rank": previous_rows[code]["rank"],
            "previous_score": previous_rows[code]["double_low_score"],
        }
        for code in dropped_codes
    ]

    changed_rows = []
    for code in sorted(set(current_rows) & set(previous_rows)):
        current_row = current_rows[code]
        previous_row = previous_rows[code]
        rank_delta = int(previous_row["rank"]) - int(current_row["rank"])
        score_delta = round(
            float(current_row["double_low_score"]) - float(previous_row["double_low_score"]),
            2,
        )
        if rank_delta == 0 and score_delta == 0:
            continue
        changed_rows.append(
            {
                "bond_code": code,
                "bond_name": current_row["bond_name"],
                "current_rank": current_row["rank"],
                "previous_rank": previous_row["rank"],
                "rank_delta": rank_delta,
                "current_score": current_row["double_low_score"],
                "previous_score": previous_row["double_low_score"],
                "score_delta": score_delta,
            }
        )

    changed_rows.sort(
        key=lambda item: (
            -item["rank_delta"],
            item["current_rank"],
            item["bond_code"],
        )
    )

    return {
        "current_scan_time": current_time,
        "previous_scan_time": previous_time,
        "new_count": len(new_rows),
        "dropped_count": len(dropped_rows),
        "changed_count": len(changed_rows),
        "new_rows": new_rows,
        "dropped_rows": dropped_rows,
        "changed_rows": changed_rows,
        "summary": (
            f"相较上一期，新进 {len(new_rows)} 只，掉出 {len(dropped_rows)} 只，"
            f"名次或分数变化 {len(changed_rows)} 只。"
        ),
    }


def _snapshot_row_lookup(rows: list[dict]) -> dict[str, dict]:
    lookup = {}
    for row in rows:
        code = str(row.get("bond_code", "")).strip().zfill(6)
        if not code:
            continue
        lookup[code] = {
            "bond_code": code,
            "bond_name": str(row.get("bond_name", "")).strip(),
            "rank": int(row.get("rank", 0) or 0),
            "double_low_score": round(float(row.get("double_low_score", 0) or 0), 2),
        }
    return lookup


def rank_market_rows(
    market_df: pd.DataFrame,
    redeem_codes: set[str],
    holdings: dict[str, dict] | set[str],
    watchlist: set[str],
    max_price: float,
    max_premium_pct: float | None,
    top_n: int,
    only_unheld: bool,
    position_filter: str = "all",
) -> list[dict]:
    holdings_lookup = _normalize_holdings_lookup(holdings)
    holding_codes = set(holdings_lookup)

    df = market_df.copy()
    df = df.dropna(subset=["bond_code", "bond_name", "price", "premium_pct"])
    df["bond_code"] = df["bond_code"].astype(str).str.strip().str.zfill(6)
    df["bond_name"] = df["bond_name"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["premium_pct"] = pd.to_numeric(df["premium_pct"], errors="coerce")
    df = df.dropna(subset=["price", "premium_pct"])
    df = df[
        ~df["bond_name"].apply(
            lambda value: any(keyword in value for keyword in EXCLUDED_NAME_KEYWORDS)
        )
    ]

    df = df[df["price"] <= max_price]
    df = df[~df["bond_code"].isin(redeem_codes)]

    if max_premium_pct is not None:
        df = df[df["premium_pct"] <= max_premium_pct]

    if only_unheld or position_filter == "unheld":
        df = df[~df["bond_code"].isin(holding_codes)]
    elif position_filter == "held":
        df = df[df["bond_code"].isin(holding_codes)]
    elif position_filter == "watchlist":
        df = df[df["bond_code"].isin(watchlist)]

    df["double_low_score"] = df["price"] + df["premium_pct"]
    df = df.sort_values(
        by=["double_low_score", "price", "premium_pct", "bond_code"],
        ascending=[True, True, True, True],
    ).head(top_n)

    rows = []
    for _, row in df.iterrows():
        code = row["bond_code"]
        holding_meta = holdings_lookup.get(code, {})
        held_quantity = holding_meta.get("quantity")
        held_avg_cost = holding_meta.get("avg_cost")
        cost_diff, cost_diff_pct, holding_status = _build_holding_metrics(
            price=float(row["price"]),
            held_avg_cost=held_avg_cost,
        )
        is_held = code in holding_codes
        signal_label = _build_signal_label(
            is_held=is_held,
            double_low_score=float(row["double_low_score"]),
            cost_diff_pct=cost_diff_pct,
        )

        rows.append(
            {
                "bond_code": code,
                "bond_name": row["bond_name"],
                "price": round(float(row["price"]), 2),
                "premium_pct": round(float(row["premium_pct"]), 2),
                "double_low_score": round(float(row["double_low_score"]), 2),
                "is_held": is_held,
                "held_quantity": held_quantity,
                "held_avg_cost": held_avg_cost,
                "held_note": holding_meta.get("note", ""),
                "cost_diff": cost_diff,
                "cost_diff_pct": cost_diff_pct,
                "holding_status": holding_status,
                "position_group": HELD_GROUP if is_held else UNHELD_GROUP,
                "signal_label": signal_label,
                "is_watchlist": code in watchlist,
            }
        )
    rows.sort(
        key=lambda item: (
            _signal_priority(item["signal_label"]),
            item["double_low_score"],
            item["price"],
            item["premium_pct"],
            item["bond_code"],
        )
    )
    for rank, item in enumerate(rows, start=1):
        item["rank"] = rank
    return rows


def _normalize_holdings_lookup(holdings: dict[str, dict] | set[str]) -> dict[str, dict]:
    if isinstance(holdings, set):
        return {code: {"quantity": None, "avg_cost": None, "note": ""} for code in holdings}

    normalized = {}
    for code, row in holdings.items():
        normalized[str(code).zfill(6)] = {
            "quantity": row.get("quantity"),
            "avg_cost": row.get("avg_cost"),
            "note": row.get("note", ""),
        }
    return normalized


def _build_holding_metrics(price: float, held_avg_cost: float | None) -> tuple[float | None, float | None, str]:
    if held_avg_cost in (None, 0):
        return None, None, ""

    cost_diff = round(price - float(held_avg_cost), 2)
    cost_diff_pct = round((cost_diff / float(held_avg_cost)) * 100, 2)
    if cost_diff > 0:
        holding_status = PROFIT_STATUS
    elif cost_diff < 0:
        holding_status = LOSS_STATUS
    else:
        holding_status = FLAT_STATUS
    return cost_diff, cost_diff_pct, holding_status


def _build_signal_label(
    is_held: bool,
    double_low_score: float,
    cost_diff_pct: float | None,
) -> str:
    if is_held:
        if cost_diff_pct is None:
            return ""
        if cost_diff_pct <= LOSS_WATCH_PCT_THRESHOLD:
            return LOSS_SIGNAL
        if abs(cost_diff_pct) <= NEAR_COST_PCT_THRESHOLD:
            return NEAR_COST_SIGNAL
        return ""

    if double_low_score <= FOCUS_SCORE_THRESHOLD:
        return FOCUS_SIGNAL
    return ""


def _signal_priority(signal_label: str) -> int:
    priorities = {
        FOCUS_SIGNAL: 0,
        LOSS_SIGNAL: 1,
        NEAR_COST_SIGNAL: 2,
        "": 3,
    }
    return priorities.get(signal_label, 3)


def build_scan_summary(
    source_name: str,
    market_count: int,
    redeem_count: int,
    candidate_rows: list[dict],
    min_expected_market_rows: int,
    source_errors: Iterable[str],
) -> dict:
    errors = [item for item in source_errors if item]
    warning_parts = []

    if market_count < min_expected_market_rows:
        warning_parts.append(
            f"当前数据源 {source_name} 仅返回 {market_count} 条记录，可能不是全市场数据。"
        )

    if errors:
        warning_parts.append("备用数据源异常: " + " | ".join(errors))

    return {
        "source_name": source_name,
        "market_count": int(market_count),
        "redeem_count": int(redeem_count),
        "candidate_count": int(len(candidate_rows)),
        "is_degraded": bool(warning_parts),
        "warning": " ".join(warning_parts),
    }


def build_spot_cov_snapshot(spot_df: pd.DataFrame, cov_df: pd.DataFrame) -> pd.DataFrame:
    spot = spot_df.copy()
    spot["bond_code"] = spot["symbol"].astype(str).str[-6:].str.zfill(6)
    spot["bond_name"] = spot["name"].astype(str).str.strip()
    spot["price"] = pd.to_numeric(spot["trade"], errors="coerce")
    spot = spot[["bond_code", "bond_name", "price"]]

    cov = cov_df.copy()
    cov["bond_code"] = cov[COL_BOND_CODE].astype(str).str.zfill(6)
    cov["premium_pct"] = pd.to_numeric(cov[COL_BOND_PREMIUM], errors="coerce")
    cov = cov[["bond_code", "premium_pct"]]

    merged = spot.merge(cov, on="bond_code", how="left")
    merged = merged.dropna(subset=["price", "premium_pct"])
    merged = merged[merged["price"] > 0]
    merged = merged[
        ~merged["bond_name"].apply(
            lambda value: any(keyword in value for keyword in EXCLUDED_SPOT_KEYWORDS)
        )
    ]
    return merged.reset_index(drop=True)


def choose_preferred_market_snapshot(
    candidates: list[tuple[pd.DataFrame, str, list[str]]],
) -> tuple[pd.DataFrame, str, list[str]]:
    if not candidates:
        raise ValueError("No market snapshot candidates available")
    return max(candidates, key=lambda item: len(item[0]))


class AkShareMarketGateway:
    def fetch_market_snapshot(
        self,
        progress_callback: Callable[[ScanProgress], None] | None = None,
    ) -> tuple[pd.DataFrame, str, list[str]]:
        if ak is None:
            raise RuntimeError("未安装 akshare。请先执行: pip install akshare pandas")

        errors: list[str] = []
        candidates: list[tuple[pd.DataFrame, str, list[str]]] = []
        cookie = os.getenv("JISILU_COOKIE", "").strip()

        _emit_scan_progress(
            progress_callback,
            "MARKET_MATRIX",
            "连接主数据源",
            9,
            "bond_zh_hs_cov_spot + bond_zh_cov",
        )
        try:
            spot_df = ak.bond_zh_hs_cov_spot()
            cov_df = ak.bond_zh_cov()
            merged_df = build_spot_cov_snapshot(spot_df, cov_df)
            if not merged_df.empty:
                candidates.append(
                    (
                        merged_df,
                        "免费合并快照 bond_zh_hs_cov_spot+bond_zh_cov",
                        errors.copy(),
                    )
                )
        except Exception as exc:
            errors.append(f"bond_zh_hs_cov_spot+bond_zh_cov: {exc}")

        _emit_scan_progress(
            progress_callback,
            "MARKET_MATRIX",
            "交叉校验集思录快照",
            24,
            "bond_cb_jsl",
            {"loaded_sources": len(candidates)},
        )
        try:
            raw_df = ak.bond_cb_jsl(cookie=cookie) if cookie else ak.bond_cb_jsl()
            normalized = self._normalize_market_df(raw_df, "集思录 bond_cb_jsl")
            candidates.append((normalized, "集思录 bond_cb_jsl", errors.copy()))
        except Exception as exc:
            errors.append(f"bond_cb_jsl: {exc}")

        _emit_scan_progress(
            progress_callback,
            "MARKET_MATRIX",
            "校验东方财富快照",
            36,
            "bond_cov_comparison",
            {"loaded_sources": len(candidates)},
        )
        try:
            raw_df = ak.bond_cov_comparison()
            normalized = self._normalize_market_df(raw_df, "东方财富 bond_cov_comparison")
            candidates.append((normalized, "东方财富 bond_cov_comparison", errors.copy()))
        except Exception as exc:
            errors.append(f"bond_cov_comparison: {exc}")

        if candidates:
            selected = choose_preferred_market_snapshot(candidates)
            _emit_scan_progress(
                progress_callback,
                "MARKET_MATRIX",
                "锁定全市场快照",
                48,
                selected[1],
                {
                    "market_count": len(selected[0]),
                    "loaded_sources": len(candidates),
                },
            )
            return selected

        raise RuntimeError("无法获取可转债市场数据；" + "；".join(errors))

    def fetch_redeem_codes(
        self,
        progress_callback: Callable[[ScanProgress], None] | None = None,
    ) -> set[str]:
        if ak is None:
            return set()

        _emit_scan_progress(
            progress_callback,
            "REDEEM_SHIELD",
            "同步强赎名单",
            51,
            "bond_cb_redeem_jsl",
        )
        try:
            redeem_df = ak.bond_cb_redeem_jsl()
        except Exception:
            return set()

        code_col = self._find_column(redeem_df, ["代码", "债券代码", "转债代码"])
        status_col = self._find_column(redeem_df, ["强赎状态", "赎回状态", "状态"])
        if not code_col or not status_col:
            return set()

        redeem_df = redeem_df[[code_col, status_col]].copy()
        redeem_df[status_col] = redeem_df[status_col].astype(str)
        mask = redeem_df[status_col].apply(
            lambda value: any(keyword in value for keyword in REDEEM_KEYWORDS)
        )
        redeem_df = redeem_df.loc[mask]
        return set(redeem_df[code_col].astype(str).str.strip().str.zfill(6))

    def _normalize_market_df(self, raw_df: pd.DataFrame, source_name: str) -> pd.DataFrame:
        if raw_df is None or raw_df.empty:
            raise ValueError(f"{source_name} 返回空数据")

        column_map = {
            "bond_code": ["代码", "转债代码", "债券代码"],
            "bond_name": ["转债名称", "债券简称", "债券名称", "名称"],
            "price": ["现价", "最新价", "转债最新价", "价格"],
            "premium_raw": ["转股溢价率", "转股价溢价率", "溢价率"],
        }

        selected = {}
        for target, candidates in column_map.items():
            actual = self._find_column(raw_df, candidates)
            if not actual:
                raise ValueError(f"{source_name} 缺少必要字段: {target}")
            selected[target] = actual

        df = raw_df[
            [
                selected["bond_code"],
                selected["bond_name"],
                selected["price"],
                selected["premium_raw"],
            ]
        ].copy()
        df.columns = ["bond_code", "bond_name", "price", "premium_raw"]
        df["bond_code"] = df["bond_code"].astype(str).str.strip().str.zfill(6)
        df["bond_name"] = df["bond_name"].astype(str).str.strip()
        df["price"] = self._to_numeric_series(df["price"])
        df["premium_pct"] = self._normalize_percent_series(df["premium_raw"])
        return df.drop(columns=["premium_raw"])

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for column in candidates:
            if column in df.columns:
                return column
        return None

    @staticmethod
    def _to_numeric_series(series: pd.Series) -> pd.Series:
        cleaned = (
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace("None", "", regex=False)
            .str.strip()
        )
        cleaned = cleaned.replace({"-": pd.NA, "nan": pd.NA, "": pd.NA})
        return pd.to_numeric(cleaned, errors="coerce")

    def _normalize_percent_series(self, series: pd.Series) -> pd.Series:
        numeric = self._to_numeric_series(series)
        if numeric.dropna().empty:
            return numeric

        median_abs = numeric.dropna().abs().median()
        if median_abs <= 1.5:
            return numeric * 100
        return numeric


class PersonalQuantAssistant:
    def __init__(
        self,
        market_gateway: AkShareMarketGateway | None = None,
        local_store: LocalStore | None = None,
        data_dir: str | Path = "data",
        max_price: float = DEFAULT_MAX_PRICE,
        min_expected_market_rows: int = DEFAULT_MIN_EXPECTED_MARKET_ROWS,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.market_gateway = market_gateway or AkShareMarketGateway()
        self.local_store = local_store or LocalStore(Path(data_dir))
        self.max_price = max_price
        self.min_expected_market_rows = min_expected_market_rows
        self.now_provider = now_provider or datetime.now

    def scan_market(
        self,
        max_premium_pct: float | None = None,
        top_n: int = DEFAULT_TOP_N,
        only_unheld: bool = False,
        position_filter: str = "all",
        progress_callback: Callable[[ScanProgress], None] | None = None,
    ) -> dict:
        _emit_scan_progress(
            progress_callback,
            "PREPARE",
            "初始化扫描环境",
            2,
            "检查本地数据文件",
        )
        self.local_store.ensure_files()
        _emit_scan_progress(
            progress_callback,
            "PREPARE",
            "本地扫描环境就绪",
            6,
            "CSV / snapshot index",
        )

        market_df, source_name, source_errors = _call_with_optional_progress(
            self.market_gateway.fetch_market_snapshot,
            progress_callback=progress_callback,
        )
        _emit_scan_progress(
            progress_callback,
            "REDEEM_SHIELD",
            "过滤强制赎回标的",
            50,
            "读取强赎状态",
        )
        redeem_codes = _call_with_optional_progress(
            self.market_gateway.fetch_redeem_codes,
            progress_callback=progress_callback,
        )
        _emit_scan_progress(
            progress_callback,
            "REDEEM_SHIELD",
            "强赎名单同步完成",
            58,
            f"已识别 {len(redeem_codes)} 只强赎转债",
            {"redeem_count": len(redeem_codes)},
        )

        _emit_scan_progress(
            progress_callback,
            "LOCAL_PORTFOLIO",
            "读取本地持仓和自选",
            60,
            "holdings.csv / watchlist.csv",
        )
        holdings_rows = self.local_store.load_holdings()
        watchlist_rows = self.local_store.load_watchlist()
        holdings = {row["bond_code"]: row for row in holdings_rows}
        watchlist = {row["bond_code"] for row in watchlist_rows}
        _emit_scan_progress(
            progress_callback,
            "LOCAL_PORTFOLIO",
            "本地组合映射完成",
            66,
            f"{len(holdings)} 个持仓 / {len(watchlist)} 个自选",
            {
                "holding_count": len(holdings),
                "watchlist_count": len(watchlist),
            },
        )

        _emit_scan_progress(
            progress_callback,
            "DOUBLE_LOW_RANK",
            "计算双低矩阵",
            68,
            "过滤、打分、排序",
        )
        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=redeem_codes,
            holdings=holdings,
            watchlist=watchlist,
            max_price=self.max_price,
            max_premium_pct=max_premium_pct,
            top_n=top_n,
            only_unheld=only_unheld,
            position_filter=position_filter,
        )
        _emit_scan_progress(
            progress_callback,
            "DOUBLE_LOW_RANK",
            "双低候选池生成",
            82,
            f"筛选 {len(rows)} 只候选",
            {"candidate_count": len(rows)},
        )

        held_candidate_count = sum(1 for row in rows if row["is_held"])
        unheld_candidate_count = sum(1 for row in rows if not row["is_held"])
        signal_candidate_count = sum(1 for row in rows if row["signal_label"])

        _emit_scan_progress(
            progress_callback,
            "SNAPSHOT_ARCHIVE",
            "生成扫描摘要",
            86,
            "汇总数据源与风险统计",
        )
        summary = build_scan_summary(
            source_name=source_name,
            market_count=len(market_df),
            redeem_count=len(redeem_codes),
            candidate_rows=rows,
            min_expected_market_rows=self.min_expected_market_rows,
            source_errors=source_errors,
        )
        summary["rows"] = rows
        summary["held_candidate_count"] = held_candidate_count
        summary["unheld_candidate_count"] = unheld_candidate_count
        summary["signal_candidate_count"] = signal_candidate_count
        summary["scan_time"] = self.now_provider().strftime("%Y-%m-%d %H:%M:%S")
        _emit_scan_progress(
            progress_callback,
            "SNAPSHOT_ARCHIVE",
            "写入本地快照",
            92,
            "持久化扫描结果",
        )
        snapshot_path = self.local_store.save_scan_snapshot(dict(summary))
        summary["snapshot_path"] = str(snapshot_path)
        _emit_scan_progress(
            progress_callback,
            "REVIEW_SYNTHESIS",
            "对比最近快照",
            96,
            "生成名次与分数变化",
        )
        review_bundle = self.get_recent_snapshot_review(limit=5)
        summary["recent_snapshots"] = review_bundle["recent_snapshots"]
        summary["snapshot_review"] = review_bundle["snapshot_review"]
        _emit_scan_progress(
            progress_callback,
            "PUBLISH",
            "扫描完成",
            100,
            "候选池与复盘已就绪",
            {
                "market_count": int(summary.get("market_count", 0)),
                "redeem_count": int(summary.get("redeem_count", 0)),
                "candidate_count": int(summary.get("candidate_count", 0)),
            },
        )
        return summary

    def get_recent_snapshot_review(self, limit: int = 5) -> dict:
        self.local_store.ensure_files()
        load_recent = getattr(self.local_store, "load_recent_snapshots", None)
        recent_snapshots = load_recent(limit=limit) if callable(load_recent) else []
        current_snapshot = recent_snapshots[0] if recent_snapshots else None
        previous_snapshot = recent_snapshots[1] if len(recent_snapshots) > 1 else None
        snapshot_review = build_snapshot_review(current_snapshot or {}, previous_snapshot)
        return {
            "recent_snapshots": recent_snapshots,
            "snapshot_review": snapshot_review,
        }

    def add_to_watchlist(self, bond_code: str, bond_name: str, note: str = "") -> None:
        self.local_store.ensure_files()
        self.local_store.upsert_watchlist(bond_code, bond_name, note)

    def remove_from_watchlist(self, bond_code: str) -> None:
        self.local_store.ensure_files()
        remove_watchlist = getattr(self.local_store, "remove_from_watchlist", None)
        if callable(remove_watchlist):
            remove_watchlist(bond_code)

    def get_watchlist(self) -> list[dict]:
        self.local_store.ensure_files()
        return self.local_store.load_watchlist()

    def add_or_update_holding(
        self,
        bond_code: str,
        bond_name: str,
        quantity: float,
        avg_cost: float | None,
        note: str = "",
    ) -> None:
        self.local_store.ensure_files()
        self.local_store.upsert_holding(bond_code, bond_name, quantity, avg_cost, note)

    def clear_holding(self, bond_code: str, bond_name: str = "") -> None:
        self.local_store.ensure_files()
        self.local_store.upsert_holding(bond_code, bond_name, 0.0, None, "")
