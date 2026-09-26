"""Operatöre giden metinlerde sayılar: Türkçe ondalık virgül ("1,6 km")."""


def num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def km(meters: float) -> str:
    return f"{num(meters / 1000)} km"


def mps(value: float) -> str:
    return f"{num(value)} m/s"
