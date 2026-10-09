"""Mergeable distributions behind histogram-like metric points.

OTLP has three shapes: explicit-bounds histograms, exponential histograms and
summaries. Points are merged per chart bucket and per series, then asked for
quantiles, min/max and buckets to draw. A cumulative point (a running total
since its process started) is first turned into the increment since the
previous point of the same series with `minus`.
"""

import dataclasses
import math
import typing


class Distribution(typing.Protocol):
    def merge(self, other: "Distribution") -> None: ...

    def minus(self, previous: "Distribution") -> "Distribution | None": ...

    def quantile(self, q: float) -> float | None: ...

    def minimum(self) -> float | None: ...

    def buckets(self) -> list[dict]: ...


@dataclasses.dataclass
class ExplicitHistogram:
    bounds: tuple[float, ...]
    # one more count than bound: the last is the +Inf overflow bucket
    counts: list[float]

    def merge(self, other: "Distribution") -> None:
        # A point re-bucketed by its exporter can't be added bucket by bucket.
        if isinstance(other, ExplicitHistogram) and self._same_layout(other):
            self.counts = [a + b for a, b in zip(self.counts, other.counts)]

    def minus(self, previous: "Distribution") -> "ExplicitHistogram | None":
        if not isinstance(previous, ExplicitHistogram) or not self._same_layout(previous):
            return None
        increment = [a - b for a, b in zip(self.counts, previous.counts)]
        if any(count < 0 for count in increment):
            return None
        return ExplicitHistogram(self.bounds, increment)

    def quantile(self, q: float) -> float | None:
        """Linear interpolation within the bucket the quantile falls in; a
        quantile in the +Inf overflow bucket reports the last finite bound."""
        total = sum(self.counts)
        if total <= 0:
            return None
        target = total * q
        cumulative = 0.0
        lower = 0.0
        for index, count in enumerate(self.counts):
            if index >= len(self.bounds):
                return self.bounds[-1] if self.bounds else 0.0
            upper = self.bounds[index]
            if cumulative + count >= target:
                if count <= 0:
                    return upper
                return lower + (upper - lower) * (target - cumulative) / count
            cumulative += count
            lower = upper
        return self.bounds[-1] if self.bounds else 0.0

    def minimum(self) -> float | None:
        for index, count in enumerate(self.counts):
            if count > 0:
                if index < len(self.bounds):
                    return self.bounds[index]
                return self.bounds[-1] if self.bounds else 0.0
        return None

    def buckets(self) -> list[dict]:
        edges = [-math.inf, *self.bounds, math.inf]
        return [
            {"lower_bound": edges[index], "upper_bound": edges[index + 1], "count": count}
            for index, count in enumerate(self.counts)
        ]

    def _same_layout(self, other: "ExplicitHistogram") -> bool:
        return self.bounds == other.bounds and len(self.counts) == len(other.counts)


@dataclasses.dataclass
class ExponentialHistogram:
    """Bucket `index` covers (base**index, base**(index + 1)], base = 2**(2**-scale);
    negative buckets mirror it below zero."""

    scale: int
    zero_count: float
    positive: dict[int, float]
    negative: dict[int, float]

    @classmethod
    def from_stored(cls, raw: dict) -> "ExponentialHistogram":
        def by_index(side: dict | None) -> dict[int, float]:
            side = side or {}
            offset = int(side.get("offset") or 0)
            return {
                offset + i: float(count)
                for i, count in enumerate(side.get("counts") or [])
                if count
            }

        return cls(
            scale=int(raw.get("scale") or 0),
            zero_count=float(raw.get("zero_count") or 0),
            positive=by_index(raw.get("positive")),
            negative=by_index(raw.get("negative")),
        )

    def at_scale(self, scale: int) -> "ExponentialHistogram":
        """The same histogram with coarser buckets: halving resolution per step
        down merges each pair of adjacent buckets exactly."""
        shift = self.scale - scale
        if shift <= 0:
            return self

        def coarsen(side: dict[int, float]) -> dict[int, float]:
            merged: dict[int, float] = {}
            for index, count in side.items():
                merged[index >> shift] = merged.get(index >> shift, 0.0) + count
            return merged

        return ExponentialHistogram(
            scale, self.zero_count, coarsen(self.positive), coarsen(self.negative)
        )

    def merge(self, other: "Distribution") -> None:
        if not isinstance(other, ExponentialHistogram):
            return
        scale = min(self.scale, other.scale)
        mine, theirs = self.at_scale(scale), other.at_scale(scale)
        self.scale = scale
        self.zero_count = mine.zero_count + theirs.zero_count
        self.positive = _add_counts(mine.positive, theirs.positive)
        self.negative = _add_counts(mine.negative, theirs.negative)

    def minus(self, previous: "Distribution") -> "ExponentialHistogram | None":
        if not isinstance(previous, ExponentialHistogram):
            return None
        # A cumulative exponential histogram only ever lowers its scale.
        scale = min(self.scale, previous.scale)
        current, before = self.at_scale(scale), previous.at_scale(scale)
        increment = ExponentialHistogram(
            scale,
            current.zero_count - before.zero_count,
            _subtract_counts(current.positive, before.positive),
            _subtract_counts(current.negative, before.negative),
        )
        if increment.zero_count < 0 or any(
            count < 0 for count in (*increment.positive.values(), *increment.negative.values())
        ):
            return None
        return increment

    def _edge(self, index: int) -> float:
        try:
            return 2.0 ** (index / 2.0**self.scale)
        except OverflowError:
            return math.inf

    def _ordered(self) -> list[tuple[float, float, float]]:
        """(lower, upper, count) for every populated bucket, ascending by value."""
        ordered = [
            (-self._edge(index + 1), -self._edge(index), count)
            for index, count in sorted(self.negative.items(), reverse=True)
        ]
        if self.zero_count:
            ordered.append((0.0, 0.0, self.zero_count))
        ordered.extend(
            (self._edge(index), self._edge(index + 1), count)
            for index, count in sorted(self.positive.items())
        )
        return ordered

    def quantile(self, q: float) -> float | None:
        ordered = self._ordered()
        total = sum(count for _, _, count in ordered)
        if total <= 0:
            return None
        target = total * q
        cumulative = 0.0
        for lower, upper, count in ordered:
            if cumulative + count >= target:
                return lower + (upper - lower) * (target - cumulative) / count
            cumulative += count
        return ordered[-1][1]

    def minimum(self) -> float | None:
        ordered = self._ordered()
        return ordered[0][0] if ordered else None

    def buckets(self) -> list[dict]:
        return [
            {"lower_bound": lower, "upper_bound": upper, "count": count}
            for lower, upper, count in self._ordered()
        ]


@dataclasses.dataclass
class Summary:
    """Quantiles as reported by the client. They can't be combined exactly, so
    merged points report the mean of each reported quantile."""

    value_sums: dict[float, float]
    value_counts: dict[float, int]

    @classmethod
    def from_stored(cls, raw: list) -> "Summary":
        pairs = [(float(q), float(v)) for q, v in raw or []]
        return cls({q: v for q, v in pairs}, {q: 1 for q, _ in pairs})

    def merge(self, other: "Distribution") -> None:
        if not isinstance(other, Summary):
            return
        for q, value in other.value_sums.items():
            self.value_sums[q] = self.value_sums.get(q, 0.0) + value
            self.value_counts[q] = self.value_counts.get(q, 0) + other.value_counts[q]

    def minus(self, previous: "Distribution") -> "Summary":
        # Reported quantiles describe a recent window, not a running total.
        return self

    def quantile(self, q: float) -> float | None:
        for reported, total in self.value_sums.items():
            if math.isclose(reported, q):
                return total / self.value_counts[reported]
        return None

    def minimum(self) -> float | None:
        return self.quantile(0.0)

    def buckets(self) -> list[dict]:
        return []


def _add_counts(a: dict[int, float], b: dict[int, float]) -> dict[int, float]:
    merged = dict(a)
    for index, count in b.items():
        merged[index] = merged.get(index, 0.0) + count
    return merged


def _subtract_counts(current: dict[int, float], before: dict[int, float]) -> dict[int, float]:
    increment = dict(current)
    for index, count in before.items():
        increment[index] = increment.get(index, 0.0) - count
    return {index: count for index, count in increment.items() if count}


def copy_of(distribution: Distribution) -> Distribution:
    """A fresh accumulator seeded with `distribution` (merging mutates in place)."""
    return dataclasses.replace(
        distribution,
        **{
            field.name: _copy_value(getattr(distribution, field.name))
            for field in dataclasses.fields(distribution)
        },
    )


def _copy_value(value: typing.Any) -> typing.Any:
    if isinstance(value, (dict, list)):
        return value.copy()
    return value
