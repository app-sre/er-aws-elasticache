from environs import env as _env

ACTION = _env.str("ACTION", default="Apply").lower()
ACTION_DELETE = ACTION == "delete"
DRY_RUN = _env.bool("DRY_RUN")
OUTPUTS_FILE = _env.str("OUTPUTS_FILE")
PLAN_FILE_JSON = _env.str("PLAN_FILE_JSON")
TERRAFORM_CMD = _env.str("TERRAFORM_CMD")
TF_VARS_FILE = _env.str("TF_VARS_FILE")
LOG_LEVEL = _env.str("LOG_LEVEL", default="INFO")
