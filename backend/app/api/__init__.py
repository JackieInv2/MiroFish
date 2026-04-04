"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
debate_bp = Blueprint('debate', __name__)

import logging as _logging

try:
    from . import graph  # noqa: E402, F401
except Exception as _e:
    _logging.getLogger('btrate').warning(f"graph routes not available: {_e}")

try:
    from . import simulation  # noqa: E402, F401
except Exception as _e:
    _logging.getLogger('btrate').warning(f"simulation routes not available: {_e}")

try:
    from . import report  # noqa: E402, F401
except Exception as _e:
    _logging.getLogger('btrate').warning(f"report routes not available: {_e}")

from . import debate  # noqa: E402, F401
