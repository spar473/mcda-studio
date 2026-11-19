"""MCDA methods. Importing this package registers the built-in methods."""

from mcda_studio.methods.ahp import AhpMethod
from mcda_studio.methods.base import Method, available_methods, get_method, register
from mcda_studio.methods.mavt import MavtMethod
from mcda_studio.methods.promethee import PrometheeMethod
from mcda_studio.methods.smaa import SmaaMethod
from mcda_studio.methods.sorting import MavtSortingMethod

register(MavtMethod())
register(MavtSortingMethod())
register(SmaaMethod())
register(PrometheeMethod())
register(AhpMethod())

__all__ = ["Method", "available_methods", "get_method", "register"]
