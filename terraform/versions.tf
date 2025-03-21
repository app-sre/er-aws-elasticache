terraform {
  required_version = "1.6.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.92.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.7.1"
    }
  }
}
