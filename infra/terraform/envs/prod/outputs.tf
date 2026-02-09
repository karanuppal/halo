output "api_url" {
  value = module.cloudrun.api_url
}

output "cloudsql_connection_name" {
  value = module.cloudsql.connection_name
}
