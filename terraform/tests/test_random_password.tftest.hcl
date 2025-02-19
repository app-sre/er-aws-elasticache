
run "password_exists" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  assert {
    condition     = random_password.this[0]
    error_message = "No random password generated"
  }

}
