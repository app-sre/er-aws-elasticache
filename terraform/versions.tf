terraform {
  required_version = "1.13.4"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.34.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.8.1"
    }
  }
}
