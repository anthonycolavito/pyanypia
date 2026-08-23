"""Computing many workers at once.

The engine is pure — a worker and a parameter set in, a result out — so
batches parallelise cleanly. `compute_many` splits the work across
processes when there is enough of it to be worth the startup cost, and
returns results in input order either way.

The pandas helpers are optional; they are only imported when used.
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Any

from pyanypia.params import Params, present_law
from pyanypia.results import Results
from pyanypia.worker import Worker

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

# Below this many workers, spawning processes costs more than it saves.
MIN_PARALLEL = 200


def compute_many(
    workers: Iterable[Worker],
    *,
    params: Params | None = None,
    alt: int = 2,
    processes: int | None = None,
    chunksize: int | None = None,
) -> list[Results]:
    """Computes every worker, in input order.

    ``processes`` defaults to one per CPU, capped by the work available;
    pass 1 to stay in this process. Results do not depend on how the work
    was divided.

    Parallel work is started with the "spawn" method, so a script calling
    this needs its entry point under ``if __name__ == "__main__":`` --
    without it each child re-imports the script and starts children of
    its own.
    """
    items = list(workers)
    if not items:
        return []
    if params is None:
        params = present_law(alt)
    n_proc = _process_count(len(items), processes)
    if n_proc <= 1:
        return [_compute_one(w, params) for w in items]
    if chunksize is None:
        chunksize = max(1, len(items) // (n_proc * 4))
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(
        processes=n_proc, initializer=_init_worker, initargs=(params,)
    ) as pool:
        return pool.map(_compute_in_pool, items, chunksize=chunksize)


def compute_iter(
    workers: Iterable[Worker],
    *,
    params: Params | None = None,
    alt: int = 2,
) -> Iterator[Results]:
    """Computes lazily in this process, for streaming over a large input
    without holding every result in memory."""
    if params is None:
        params = present_law(alt)
    for w in workers:
        yield _compute_one(w, params)


def _process_count(n_items: int, processes: int | None) -> int:
    if processes is not None:
        return max(1, processes)
    if n_items < MIN_PARALLEL:
        return 1
    return max(1, min(os.cpu_count() or 1, n_items))


def _compute_one(worker: Worker, params: Params) -> Results:
    from pyanypia.engine.compute import calculate
    from pyanypia.results import results_from_context

    return results_from_context(calculate(worker, params))


# Pool workers are handed the parameter set once and reuse it, rather
# than it travelling with every case: it is far larger than a worker and
# far more expensive to assemble than one case is to compute.
#
# It has to be the caller's own set, not one rebuilt from `alt`. Rebuilding
# it lost any reform the caller passed, so a batch of 200 quietly answered
# under present law while the same batch of 199, which never left this
# process, answered under the reform.
_POOL_PARAMS: Params | None = None


def _init_worker(params: Params) -> None:  # pragma: no cover - subprocess
    global _POOL_PARAMS
    _POOL_PARAMS = params


def _compute_in_pool(worker: Worker) -> Results:  # pragma: no cover
    assert _POOL_PARAMS is not None
    return _compute_one(worker, _POOL_PARAMS)


# ------------------------------------------------------------- dataframes

DEFAULT_MAPPING = {
    "dob": "dob",
    "sex": "sex",
    "benefit_type": "benefit_type",
    "entitlement": "entitlement",
    "benefit_date": "benefit_date",
    "death_date": "death_date",
}


def workers_from_frame(
    df: pd.DataFrame,
    *,
    mapping: dict[str, str] | None = None,
    earnings: str | Sequence[str] | None = None,
    year_column: str | None = None,
    amount_column: str | None = None,
    id_column: str | None = None,
) -> list[Worker]:
    """Builds workers from a DataFrame.

    Earnings come either from wide columns — one per year, named by the
    year — or from a long frame, where ``year_column`` and
    ``amount_column`` name the year and amount and ``id_column`` groups
    the rows into workers.
    """
    if year_column is not None:
        return _workers_from_long(
            df, year_column, amount_column, id_column, mapping
        )
    return _workers_from_wide(df, earnings, mapping)


def _field_values(
    row: Any, mapping: dict[str, str] | None
) -> dict[str, Any]:
    mapping = {**DEFAULT_MAPPING, **(mapping or {})}
    out: dict[str, Any] = {}
    for field, column in mapping.items():
        if column in row and row[column] is not None:
            value = row[column]
            if value != value:  # NaN
                continue
            out[field] = value
    return out


def _year_columns(
    df: pd.DataFrame, earnings: str | Sequence[str] | None
) -> list[Any]:
    if earnings is None:
        return [c for c in df.columns if _as_year(c) is not None]
    if isinstance(earnings, str):
        return [c for c in df.columns if str(c).startswith(earnings)]
    return list(earnings)


def _as_year(column: Any) -> int | None:
    text = str(column)
    digits = text[-4:]
    if digits.isdigit() and 1900 <= int(digits) <= 2200:
        return int(digits)
    return None


def _workers_from_wide(
    df: pd.DataFrame,
    earnings: str | Sequence[str] | None,
    mapping: dict[str, str] | None,
) -> list[Worker]:
    columns = _year_columns(df, earnings)
    if not columns:
        raise ValueError(
            "no earnings columns found; name them by year or pass `earnings`"
        )
    parsed = {c: _as_year(c) for c in columns}
    missing = [c for c, y in parsed.items() if y is None]
    if missing:
        raise ValueError(f"earnings columns without a year: {missing}")
    years: dict[Any, int] = {c: y for c, y in parsed.items() if y is not None}
    out = []
    for _, row in df.iterrows():
        amounts = {
            years[c]: float(row[c])
            for c in columns
            if row[c] is not None and row[c] == row[c]
        }
        out.append(Worker(earnings=amounts, **_field_values(row, mapping)))
    return out


def _workers_from_long(
    df: pd.DataFrame,
    year_column: str,
    amount_column: str | None,
    id_column: str | None,
    mapping: dict[str, str] | None,
) -> list[Worker]:
    if amount_column is None or id_column is None:
        raise ValueError(
            "long format needs `amount_column` and `id_column` as well"
        )
    out = []
    for _, group in df.groupby(id_column, sort=False):
        first = group.iloc[0]
        amounts = {
            int(r[year_column]): float(r[amount_column])
            for _, r in group.iterrows()
        }
        out.append(Worker(earnings=amounts, **_field_values(first, mapping)))
    return out


def compute_frame(
    df: pd.DataFrame,
    *,
    mapping: dict[str, str] | None = None,
    earnings: str | Sequence[str] | None = None,
    year_column: str | None = None,
    amount_column: str | None = None,
    id_column: str | None = None,
    params: Params | None = None,
    alt: int = 2,
    processes: int | None = None,
) -> pd.DataFrame:
    """Computes a DataFrame of workers and returns a frame of results,
    one row per worker in input order."""
    import pandas as pd

    workers = workers_from_frame(
        df,
        mapping=mapping,
        earnings=earnings,
        year_column=year_column,
        amount_column=amount_column,
        id_column=id_column,
    )
    results = compute_many(
        workers, params=params, alt=alt, processes=processes
    )
    rows = [
        {
            "insured": r.insured,
            "insured_code": r.fully_insured_code,
            "elig_year": r.elig_year,
            "aime": r.aime,
            "pia": r.pia,
            "mfb": r.mfb,
            "monthly_benefit": r.monthly_benefit,
            "method": r.method,
            "months_reduction_or_credit": r.months_reduction_or_credit,
        }
        for r in results
    ]
    index = None
    if year_column is not None and id_column is not None:
        index = pd.Index(
            list(dict.fromkeys(df[id_column])), name=id_column
        )
    elif len(rows) == len(df):
        index = df.index
    return pd.DataFrame(rows, index=index)
