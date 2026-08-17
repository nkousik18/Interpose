# terraform/aws-eks

Terraform module provisioning Interpose's full AWS reference environment
(`docs/INTERPOSE_SCOPING.md` Section 11.6): a VPC, an EKS cluster + managed node
group, RDS Postgres (the audit log's hot tier, Section 10.7), ElastiCache Redis
(session state / rate limiting / HITL queue, Section 6.8), an S3 audit-archive
bucket with a Glacier lifecycle policy, IRSA for the gateway's pod-level AWS access,
and CloudWatch logging/alarms.

**Status: built and `terraform validate`-clean, not yet applied against real AWS.**
Phase 4's deliberate scope for this module (`docs/project/SESSION_LOG.md`): write and
statically validate the module now; the live `terraform apply` → `helm install` →
smoke test → `terraform destroy` cycle Section 14.8's Day 17 describes is a separate,
explicitly-approved step given the real ongoing AWS cost involved (see below).

## Hand-rolled, not a community module

Every resource here is a plain `aws_*` Terraform resource, not the community
`terraform-aws-modules/vpc` or `terraform-aws-modules/eks` module. Same reasoning
this project already applied to the Helm chart's embedded Postgres/Redis
(`charts/interpose/values.yaml`'s `postgres.embedded` comment): an external module
dependency buys nothing a few dozen resources here don't already cover plainly, for
a module whose whole point is demonstrating real understanding of what an
EKS-ready AWS environment actually needs -- not abstracting it away behind someone
else's module the day it's written.

## Structure

```
terraform/aws-eks/
├── main.tf              # shared data sources (AZs, caller identity, region) -- no provider block, see its own comment
├── versions.tf           # Terraform + provider version pinning
├── variables.tf          # module inputs, all with sane defaults
├── outputs.tf            # everything a downstream Helm install needs
├── locals.tf              # naming convention, common tags
├── vpc.tf                # VPC, public/private subnets, NAT, route tables
├── eks.tf                 # EKS cluster + managed node group + IRSA's OIDC provider
├── rds.tf                 # RDS Postgres (audit log hot tier)
├── elasticache.tf         # ElastiCache Redis (toggle: enable_elasticache)
├── s3.tf                  # audit archive bucket + Glacier lifecycle
├── iam.tf                 # IRSA role for the gateway's Kubernetes ServiceAccount
├── security_groups.tf     # node / RDS / Redis security groups
├── kms.tf                 # customer-managed encryption keys (toggle: enable_custom_kms)
├── monitoring.tf          # CloudWatch log group + a representative RDS alarm pair
└── examples/
    └── minimal/
        └── main.tf         # EKS + RDS + S3 only -- ElastiCache and custom KMS off
```

## Usage

```sh
cd terraform/aws-eks/examples/minimal
terraform init      # local state by default; see main.tf's commented S3 backend block
terraform plan      # needs real AWS credentials (any method the AWS provider supports)
terraform apply
```

Or instantiate the module directly from another root module:

```hcl
module "interpose_eks" {
  source = "github.com/<you>/Interpose//terraform/aws-eks"

  cluster_name       = "interpose"
  environment        = "prod"
  enable_elasticache = true   # a real ElastiCache Redis, not in-cluster
  enable_custom_kms  = true   # dedicated KMS keys, not each service's own default
}
```

After `apply`, point `kubectl`/`helm` at the new cluster with the `configure_kubectl`
output, then `helm install interpose ./charts/interpose` with a values overlay
setting `postgres.embedded=false`/`redis.embedded=false` and the RDS/Redis
connection details this module's own outputs provide (`rds_address`,
`rds_secret_arn`, `redis_endpoint`, `redis_secret_arn`).

## Cost estimate

**~$150-200/month** at the default configuration (`examples/minimal/`'s own
defaults: `t3.large` nodes × 2, `db.t4g.medium` RDS, single NAT Gateway, no
ElastiCache, no custom KMS -- matching Section 11.6's own number exactly). Rough
breakdown at US East pricing:

| Component | Est. monthly |
|---|---|
| EKS control plane | ~$73 (flat $0.10/hr) |
| 2× `t3.large` nodes | ~$120 |
| 1× NAT Gateway (`single_nat_gateway=true`) | ~$33 + data processing |
| `db.t4g.medium` RDS, 20GB gp3 | ~$50 |
| S3 (audit archive, low volume) | a few dollars |
| **Total** | **~$275-300** before optimization |

Real total lands closer to the doc's $150-200 estimate at t3.medium/single-AZ
tradeoffs a real deployer would make; the defaults above favor a realistic reference
shape over the cheapest possible one. `enable_elasticache=true` adds a `cache.t4g.small`
ElastiCache node (~$25/month); `var.single_nat_gateway=false` roughly doubles NAT cost
for real multi-AZ HA.

**This module provisions real, billed AWS resources the moment `terraform apply`
succeeds** -- `terraform plan` alone costs nothing (beyond the AWS API calls it makes
to check current state, which are free), but `apply` starts the clock immediately, not
after Kubernetes workloads are deployed onto it.

## Teardown safety

```sh
# 1. Uninstall the Helm release first -- lets Kubernetes-managed resources (any
#    LoadBalancer Services, their AWS ELBs) drain and delete cleanly. Terraform
#    doesn't know about anything Helm/kubectl created directly against the
#    cluster's own API, so skipping this step can leave orphaned ELBs that
#    `terraform destroy` won't find or bill you for cleaning up.
helm uninstall interpose

# 2. Then tear down the AWS infrastructure itself.
cd terraform/aws-eks/examples/minimal
terraform destroy
```

**The S3 audit archive bucket is `force_destroy = false`** (the default -- not set
explicitly anywhere in this module, deliberately): `terraform destroy` will fail on
a non-empty audit bucket rather than silently deleting real audit records. Empty it
explicitly first if you genuinely want it gone (`aws s3 rm s3://<bucket> --recursive`),
or leave it -- `terraform destroy -target` everything except the bucket is the safer
default motion for a compliance-relevant data store.

**RDS's final snapshot is skipped by default** (`skip_final_snapshot = true`, rds.tf)
-- this module's own defaults target "cheap to tear down while learning it," not a
production data-retention policy. A real production teardown should not rely on this
module's defaults for that decision.

## Named gaps (deliberately not built)

- **No live-verified `apply`/`destroy` cycle yet** -- see "Status" above. This
  module's own correctness is validated statically (`terraform validate`,
  `terraform fmt -check`, CI) but has not yet provisioned a real EKS cluster.
- **No cluster autoscaler / Karpenter** -- `var.node_min_size`/`node_max_size` set
  the node group's own scaling bounds, but nothing watches pod scheduling pressure
  and adjusts it automatically. `charts/interpose/values.yaml`'s `replicaCount`
  comment already notes the gateway itself doesn't need this yet either.
- **No Terraform Cloud/remote-state locking configured by default** -- `examples/minimal/`
  shows the S3 backend block, commented out; wiring up a real state bucket + DynamoDB
  lock table is a one-time setup step left to whoever actually runs this.
