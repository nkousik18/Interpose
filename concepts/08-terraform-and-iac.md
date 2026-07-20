# Terraform and "Infrastructure as Code"

## The core idea

**Infrastructure as Code (IaC)** means describing your infrastructure (servers, networks,
managed databases, Kubernetes clusters) in text files that get checked into version control,
instead of clicking through a cloud provider's web console to create things by hand. The text
is the source of truth; running a tool against it makes reality match the description — add
what's missing, change what's different, and (if you ask it to) remove what's no longer
declared.

**Terraform** (by HashiCorp) is the most widely used tool for this, and it's
**cloud-provider-agnostic** — the same tool and language (HCL, HashiCorp Configuration Language)
can provision AWS resources, Google Cloud resources, Kubernetes resources, and hundreds of
other systems, each via a "provider" plugin.

## Why it matters, beyond convenience

- **Repeatable**: the exact same cluster can be created, destroyed, and recreated identically —
  no "I forgot which checkbox I clicked six months ago."
- **Reviewable**: infrastructure changes go through the same code-review workflow as
  application code (a pull request), instead of being invisible clicks in a console.
- **Reversible on purpose**: `terraform destroy` tears down exactly what was declared. This
  matters a lot for a portfolio project — real AWS infrastructure costs money by the hour, so
  the plan (Section 14.8, Phase 4) is explicitly: `terraform apply` → smoke test → `terraform
  destroy`, not "leave a cluster running for a month."

## Where it fits in Sentinel specifically

Terraform's job here is narrow and specific: provision a **real AWS EKS cluster** (Elastic
Kubernetes Service — Amazon's managed Kubernetes) — the production-shaped counterpart to the
local `kind` cluster we already tested (see [[07-what-is-kubernetes]]). Terraform doesn't
deploy Sentinel itself onto that cluster — that's Helm's job, layered on top once the cluster
exists. Two different tools, two different layers: Terraform answers "does the cluster exist,"
Helm answers "what's running inside it."

This is Phase 4 (Week 4) work in the roadmap — we've only installed and verified the CLI so
far (`terraform --version` → `1.15.8`). We'll go deeper on HCL syntax and the actual EKS module
when we get there.

## One thing worth flagging now

Terraform used to be installable straight from Homebrew's main repository; HashiCorp changed
its license (BSL) a few years back and pulled it from `homebrew-core` into their own tap
(`hashicorp/tap`). That's why installation needed an extra `brew tap hashicorp/tap` step first
— a small but real example of how open-source licensing decisions can ripple into tooling
availability, which is a reasonable thing to be aware of if this ever comes up.

## Related

- [[07-what-is-kubernetes]]
- [[06-containers-and-docker]]
