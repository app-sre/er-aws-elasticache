from collections.abc import Sequence
from typing import Any, Literal, Self

from external_resources_io.input import AppInterfaceProvision
from pydantic import BaseModel, field_validator, model_validator


class ElasticacheLogDeliveryConfiguration(BaseModel):
    """Data model for AWS Elasticache log delivery configuration"""

    destination: str
    destination_type: str
    log_type: str
    log_format: str


class Parameter(BaseModel):
    """db_parameter_group_parameter"""

    name: str
    value: Any
    apply_method: Literal["immediate", "pending-reboot"] | None = None

    @field_validator("value", mode="before")
    @classmethod
    def transform(cls, v: Any) -> str:  # noqa: ANN401
        """Values come as int|str|float|bool from App-Interface, but terraform only allows str"""
        return str(v)


class ParameterGroup(BaseModel):
    "db_parameter_group"

    family: str
    name: str
    description: str
    parameters: Sequence[Parameter]


class ElasticacheData(BaseModel):
    """Data model for AWS Elasticache"""

    # app-interface
    region: str
    identifier: str
    output_resource_name: str | None = None
    output_prefix: str
    tags: dict[str, Any] | None = None
    default_tags: Sequence[dict[str, Any]] | None = None

    # service updates related
    environment: str = "production"
    service_updates_enabled: bool = True
    service_updates_severities: Sequence[str] = ["critical", "important"]
    service_updates_cooldown_days: int | None = None

    # aws_elasticache_replication_group
    apply_immediately: bool = False
    at_rest_encryption_enabled: bool | None = None
    auto_minor_version_upgrade: bool | None = None
    automatic_failover_enabled: bool | None = None
    reset_password: str | None = None
    replication_group_description: str = "elasticache replication group"
    engine: str
    engine_version: str
    log_delivery_configuration: Sequence[ElasticacheLogDeliveryConfiguration] | None = (
        None
    )
    maintenance_window: str | None = None
    multi_az_enabled: bool | None = None
    node_type: str
    notification_topic_arn: str | None = None
    number_cache_clusters: int | None = None
    num_node_groups: int | None = None
    parameter_group: ParameterGroup | None = None
    parameter_group_name: str | None = None
    port: int | None = None
    availability_zones: Sequence[str] | None = None
    replicas_per_node_group: int | None = None
    replication_group_id: str
    security_group_ids: Sequence[str] | None = None
    snapshot_retention_limit: int | None = None
    snapshot_window: str | None = None
    subnet_group_name: str | None = None
    transit_encryption_enabled: bool | None = None
    transit_encryption_mode: str | None = None

    @model_validator(mode="after")
    def automatic_failover(self) -> Self:
        """If enabled, number_cache_clusters must be greater than 1. Must be enabled for Redis (cluster mode enabled) replication groups."""
        if (
            self.automatic_failover_enabled
            and self.number_cache_clusters is not None
            and self.number_cache_clusters < 2  # noqa: PLR2004
        ):
            raise ValueError(
                "Automatic failover is not supported for clusters with less than 2 nodes. Set number_cache_clusters to 2 or more."
            )
        return self

    @model_validator(mode="after")
    def no_auto_minor_version_upgrade_for_redis_five(self) -> Self:
        """Auto minor version upgrade is not supported for Redis 5.x"""
        if (
            self.engine == "redis"
            and self.engine_version.startswith("5.")
            and self.auto_minor_version_upgrade
        ):
            raise ValueError(
                "Auto minor version upgrade is not supported for Redis 5.x"
            )
        return self

    @model_validator(mode="after")
    def multi_az_needs_automatic_failover(self) -> Self:
        """Multi-AZ is only supported with automatic failover enabled"""
        if self.multi_az_enabled and not self.automatic_failover_enabled:
            raise ValueError(
                "Multi-AZ is only supported with automatic failover enabled. Either enable 'automatic_failover_enabled' or disable 'multi_az_enabled'"
            )
        return self

    @model_validator(mode="after")
    def number_cache_clusters_vs_num_node_groups(self) -> Self:
        """If num_node_groups is set, number_cache_clusters must be unset"""
        if self.num_node_groups and self.number_cache_clusters:
            raise ValueError(
                "number_cache_clusters and cluster_mode.num_node_groups are mutually exclusive."
            )
        return self

    @model_validator(mode="after")
    def no_availability_zones_for_num_node_groups(self) -> Self:
        """Preferred cache cluster AZs are not supported when num_node_groups is set"""
        if self.num_node_groups and self.availability_zones:
            raise ValueError(
                "availability_zones and cluster_mode.num_node_groups are mutually exclusive. Use the subnet_group_name to control the availability zones."
            )
        return self

    @model_validator(mode="after")
    def no_snapshot_retention_limit_for_cache_t1_micro(self) -> Self:
        """Snapshot retention limit is not supported for cache.t1.micro"""
        if self.node_type == "cache.t1.micro" and self.snapshot_retention_limit:
            raise ValueError(
                "Snapshot retention limit is not supported for cache.t1.micro"
            )
        return self


class AppInterfaceInput(BaseModel):
    """Input model for AWS Elasticache"""

    data: ElasticacheData
    provision: AppInterfaceProvision
