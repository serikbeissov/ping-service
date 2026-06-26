from pathlib import Path

from fastapi.templating import Jinja2Templates

from .config import settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["app_title"] = settings.app_title
