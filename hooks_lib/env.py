from environs import env as _env


class MetaEnv(type):
    """MetaEnv."""

    def __getattribute__(cls, name: str) -> str | bool:  # noqa: PLR0911
        """Get and parse the requested environment variable."""
        match name:
            case "ACTION":
                return _env.str("ACTION", default="Apply").lower()
            case "DRY_RUN":
                return _env.bool("DRY_RUN")
            case "LOG_LEVEL":
                return _env.str("LOG_LEVEL", default="INFO")
            case "OUTPUTS_FILE":
                return _env.str("OUTPUTS_FILE")
            case "PLAN_FILE_JSON":
                return _env.str("PLAN_FILE_JSON")
            case "TERRAFORM_CMD":
                return _env.str("TERRAFORM_CMD")
            case "TF_VARS_FILE":
                return _env.str("TF_VARS_FILE")
            case _:
                raise ValueError(f"Unknown environment variable: {name}")


class Env(metaclass=MetaEnv):
    """Environment Variables."""

    # Define of all used environment variables with their types
    ACTION: str
    DRY_RUN: bool
    LOG_LEVEL: str
    OUTPUTS_FILE: str
    PLAN_FILE_JSON: str
    TERRAFORM_CMD: str
    TF_VARS_FILE: str
