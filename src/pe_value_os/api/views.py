"""Public server-rendered view interface, split by review responsibility."""

from .portfolio_views import evidence_page as evidence_page
from .portfolio_views import home_page as home_page
from .portfolio_views import login_page as login_page
from .presentation import CSS as CSS
from .presentation import page as page
from .review_views import kpi_page as kpi_page
from .review_views import review_page as review_page
