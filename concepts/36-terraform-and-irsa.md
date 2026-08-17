# Terraform, and IRSA: why a pod can have its own AWS identity

Phase 4, Day 17 (`docs/ROADMAP.md`; `docs/INTERPOSE_SCOPING.md` Section 11.6). First
real use of Terraform in this project -- installed back in Phase 0 alongside
`kubectl`/`helm`/`kind`, unused until now.

## What Terraform actually is

Every other tool this project uses so far is *imperative*: `kubectl apply`, `docker
build`, `helm install` all describe an action to take, run once, done. Terraform is
*declarative*: a `.tf` file describes what should exist (a VPC with these subnets, an
RDS instance with this size), and `terraform plan`/`apply` compute the create/update/
delete steps needed to make AWS match that description -- diffing against a state
file (`terraform.tfstate`) that records what Terraform believes is already there.
Run `apply` again with no changes, and Terraform does nothing; change one variable,
and it recomputes exactly what needs to move.

That state file is why `terraform destroy` is safe in a way `rm -rf` isn't: Terraform
only ever touches resources it's tracking in state, in the order its own dependency
graph says is safe (subnets before the instances that live in them, in reverse order
on the way down).

## A reusable module never configures its own provider

`terraform/aws-eks/` is a *module* -- meant to be instantiated from somewhere else
(`examples/minimal/main.tf`, or a real production root module) via `module "..." {
source = "..." }`. It has zero `provider "aws" { ... }` blocks anywhere in it. That's
deliberate, not an oversight: provider configuration (which region, which
credentials) is the *root* module's job. A reusable module that hardcoded its own
provider block would either conflict with whatever the root module configures, or
force every caller into Terraform's awkward "provider passing" mechanism -- both
defeat the point of writing something reusable in the first place. `main.tf`'s own
comment spells this out; `examples/minimal/main.tf` is where the real `provider`
block and real `region` variable live, because that file *is* a root module.

## Why hand-rolled resources, not `terraform-aws-modules/vpc`/`eks`

The community modules are excellent and what most real teams reach for. This module
deliberately doesn't use them -- same reasoning already applied to the Helm chart's
embedded Postgres/Redis (`charts/interpose/values.yaml`'s own comment on
`postgres.embedded`): an external module dependency buys nothing that three dozen
plain `aws_vpc`/`aws_subnet`/`aws_eks_cluster` resources don't already cover, for a
module whose entire purpose is demonstrating real, first-principles understanding of
what an EKS-ready AWS environment needs -- not delegating that understanding to
someone else's abstraction on day one.

## IRSA: a pod's own IAM identity, not the node's

Before IRSA (IAM Roles for Service Accounts), a pod's AWS permissions came from
whatever IAM role its EC2 node's instance profile had -- meaning every pod scheduled
onto a given node shared the same AWS permissions, whether it needed S3 access or
not. IRSA lets one specific Kubernetes `ServiceAccount` assume one specific,
narrowly-scoped IAM role, independent of the node it happens to land on.

The mechanism (`eks.tf`, `iam.tf`): EKS gives every cluster an OIDC (OpenID Connect)
issuer URL, which `aws_iam_openid_connect_provider` registers as a *trusted identity
provider* in IAM. An IAM role's trust policy can then say "trust a web identity token
from this OIDC provider, but only if it claims to be
`system:serviceaccount:<namespace>:<name>`" -- exactly `iam.tf`'s
`gateway_irsa_assume` policy document. When a pod using that ServiceAccount starts,
EKS's own webhook injects a short-lived token matching that identity; the AWS SDK
inside the pod exchanges it for real, temporary credentials via `sts:AssumeRoleWithWebIdentity`.
The gateway's own code never handles a long-lived AWS access key at all -- it's pure
trust-relationship plumbing between EKS and IAM, this module's `gateway` role scoped
to exactly two things it needs: read the RDS/Redis credentials from Secrets Manager,
read/write the S3 audit archive.

## A real schema bug `terraform validate` caught, not a live apply

Writing `aws_eks_cluster`'s `encryption_config` block, a wrong recollection produced
`provider_key_arn = aws_kms_key.eks[0].arn` as a flat attribute. The real schema
nests it: `encryption_config { provider { key_arn = ... } resources = [...] } }`.
`terraform validate` caught this immediately -- "Unsupported argument" -- without
ever touching AWS. That's the whole value of `terraform validate` as a check this
phase's scope (build and statically validate, no live `apply` without a separate,
explicit go-ahead) can actually lean on: it verifies a configuration's internal
consistency -- every resource's schema, every reference between resources, every
required argument -- entirely offline. What it *can't* catch: a resource that's
schema-valid but would fail at apply time for an AWS-side reason (a quota limit, a
region that doesn't support a chosen instance type, an IAM policy that's syntactically
fine but wrong in effect). That gap is exactly why this phase stops at `validate`,
not `apply` -- the real proof only comes from a live run against real AWS, deferred
to its own explicit, cost-aware decision.

## The embedded-vs-external pattern, once more

`var.enable_elasticache` and `var.enable_custom_kms` are the same toggle shape the
Helm chart already established for Postgres/Redis and, later, the OTel
Collector/Prometheus pair: `false` (examples/minimal/'s own setting) means "skip this
AWS-managed piece, something simpler stands in for it" -- an in-cluster Redis instead
of ElastiCache, each service's own default encryption instead of a dedicated
customer-managed KMS key. `true` is the fuller reference shape a real production
instantiation would set. One pattern, applied consistently everywhere this project
has ever had to choose between "the chart/module manages this dependency" and "bring
your own."
