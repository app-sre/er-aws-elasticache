from cdktf import (
    Fn,
    S3Backend,
    TerraformOutput,
    TerraformResourceLifecycle,
    TerraformStack,
)
from cdktf_cdktf_provider_aws.elasticache_parameter_group import (
    ElasticacheParameterGroup,
    ElasticacheParameterGroupParameter,
)
from cdktf_cdktf_provider_aws.elasticache_replication_group import (
    ElasticacheReplicationGroup,
    ElasticacheReplicationGroupLogDeliveryConfiguration,
)
from cdktf_cdktf_provider_aws.provider import AwsProvider
from cdktf_cdktf_provider_random.password import Password
from cdktf_cdktf_provider_random.provider import RandomProvider
from constructs import Construct

from .app_interface_input import AppInterfaceInput


class ElasticacheStack(TerraformStack):
    """AWS Elasticache stack"""

    def __init__(
        self, scope: Construct, id_: str, app_interface_input: AppInterfaceInput
    ) -> None:
        super().__init__(scope, id_)
        self.data = app_interface_input.data
        self.provision = app_interface_input.provision
        self._init_providers()
        self._run()

    def _init_providers(self) -> None:
        S3Backend(
            self,
            bucket=self.provision.module_provision_data.tf_state_bucket,
            key=self.provision.module_provision_data.tf_state_key,
            encrypt=True,
            region=self.provision.module_provision_data.tf_state_region,
            dynamodb_table=self.provision.module_provision_data.tf_state_dynamodb_table,
            profile="external-resources-state",
        )
        AwsProvider(
            self,
            f"aws.{self.data.region}",
            region=self.data.region,
            default_tags=self.data.default_tags,
        )
        RandomProvider(self, "Random")

    def _create_parameter_group(self) -> ElasticacheParameterGroup | None:
        if self.data.parameter_group:
            return ElasticacheParameterGroup(
                self,
                self.data.parameter_group.name,
                family=self.data.parameter_group.family,
                name=self.data.parameter_group.name,
                description=self.data.parameter_group.description,
                parameter=[
                    ElasticacheParameterGroupParameter(
                        name=param.name,
                        value=param.value,
                    )
                    for param in self.data.parameter_group.parameters
                ],
                tags=self.data.tags,
                lifecycle=TerraformResourceLifecycle(create_before_destroy=True),
            )
        return None

    def _create_elasticache(
        self, parameter_group: ElasticacheParameterGroup | None
    ) -> ElasticacheReplicationGroup:
        auth_token = None
        if self.data.transit_encryption_enabled:
            auth_token = Password(
                self,
                id=f"{self.data.identifier}-password",
                length=20,
                keepers={"reset_password": self.data.reset_password}
                if self.data.reset_password
                else None,
            ).result
        return ElasticacheReplicationGroup(
            self,
            self.data.identifier,
            apply_immediately=self.data.apply_immediately,
            at_rest_encryption_enabled=self.data.at_rest_encryption_enabled,
            # no idea why this is a string
            auto_minor_version_upgrade=str(
                self.data.auto_minor_version_upgrade
            ).lower(),
            automatic_failover_enabled=self.data.automatic_failover_enabled,
            auth_token=auth_token,
            description=self.data.replication_group_description,
            engine=self.data.engine,
            engine_version=self.data.engine_version,
            log_delivery_configuration=[
                ElasticacheReplicationGroupLogDeliveryConfiguration(
                    destination=ldc.destination,
                    destination_type=ldc.destination_type,
                    log_format=ldc.log_format,
                    log_type=ldc.log_type,
                )
                for ldc in self.data.log_delivery_configuration or []
            ],
            maintenance_window=self.data.maintenance_window,
            multi_az_enabled=self.data.multi_az_enabled,
            node_type=self.data.node_type,
            notification_topic_arn=self.data.notification_topic_arn,
            num_cache_clusters=self.data.number_cache_clusters,
            num_node_groups=self.data.num_node_groups,
            parameter_group_name=self.data.parameter_group_name,
            port=self.data.port,
            preferred_cache_cluster_azs=self.data.availability_zones,
            replicas_per_node_group=self.data.replicas_per_node_group,
            replication_group_id=self.data.replication_group_id,
            security_group_ids=self.data.security_group_ids,
            snapshot_retention_limit=self.data.snapshot_retention_limit,
            snapshot_window=self.data.snapshot_window,
            subnet_group_name=self.data.subnet_group_name,
            transit_encryption_enabled=self.data.transit_encryption_enabled,
            transit_encryption_mode=self.data.transit_encryption_mode,
            tags=self.data.tags,
            depends_on=[parameter_group] if parameter_group else None,
        )

    def _outputs(self, elasticache: ElasticacheReplicationGroup) -> None:
        TerraformOutput(
            self,
            self.data.output_prefix + "__db_endpoint",
            value=Fn.conditional(
                elasticache.cluster_enabled,
                elasticache.configuration_endpoint_address,
                elasticache.primary_endpoint_address,
            ),
            sensitive=False,
        )

        TerraformOutput(
            self,
            self.data.output_prefix + "__db_port",
            value=elasticache.port,
            sensitive=False,
        )

        TerraformOutput(
            self,
            self.data.output_prefix + "__db_auth_token",
            value=elasticache.auth_token,
            sensitive=True,
        )

    def _run(self) -> None:
        """Run the stack"""
        parameter_group = self._create_parameter_group()
        elasticache = self._create_elasticache(parameter_group)
        self._outputs(elasticache)
