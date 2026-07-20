# What Kubernetes actually is (and why we need it here)

## The problem it solves

Once an application is split into containers (see [[06-containers-and-docker]]), a new problem
shows up at any real scale: *something* has to decide which physical machine each container
runs on, restart it if it crashes, give it a stable network address, roll out new versions
without downtime, and scale it up or down. Doing that by hand across many machines doesn't
work. **Kubernetes (K8s)** is software that does that job — a "container orchestrator." You
describe the *desired state* ("I want 3 copies of this container running, each with this much
memory") and Kubernetes continuously works to make reality match that description.

The name gets shortened to "K8s" because there are 8 letters between the K and the s —
that's a real, if slightly silly, convention worth knowing.

## Why Interpose needs it

The scoping doc targets Kubernetes as the deployment platform (Section 6.11) because it's the
default assumption at essentially every enterprise the project targets (Section 3's "Room 2" —
Deloitte, MassMutual, Ford, etc. all run their platforms on K8s). Being able to say "I designed
and deployed this on Kubernetes, with a Helm chart and a Terraform-provisioned cluster" is
directly one of the three named resume-gap items the whole project exists to close.

## The pieces we just used, and how they relate

- **A cluster**: one or more machines ("nodes") running Kubernetes together — one acts as the
  **control plane** (the brain: decides what goes where), others run the actual application
  containers.
- **`kubectl`**: the command-line client for *talking to* a running cluster — "show me the
  nodes," "show me what's running," "apply this configuration." It doesn't run anything itself;
  it just sends instructions to a cluster's control plane, the same client/daemon split as
  Docker.
- **`kind`** ("Kubernetes IN Docker"): a tool that runs an *entire* small Kubernetes cluster
  using Docker containers as the "nodes," entirely on your laptop. It exists so you can develop
  against a real Kubernetes cluster without needing real cloud infrastructure (and its cost) for
  every iteration. This is strictly a **local development** tool — the scoping doc's plan is
  `kind` now, real AWS EKS (Elastic Kubernetes Service) later, in Week 4 / Phase 4.
- **Helm**: covered in its own doc once we actually write a chart — think of it for now as "a
  package manager for Kubernetes configuration," so we don't hand-write every low-level
  Kubernetes YAML file for each deploy.

## What we just verified, concretely

```
kind create cluster --name interpose-smoketest   # spun up a real (if tiny) K8s cluster in Docker
kubectl get nodes                                # confirmed the control plane came up, Ready
kind delete cluster --name interpose-smoketest    # tore it down again, cleanly
```

That loop — create, inspect, destroy — is the same loop we'll run constantly during
development: throwaway clusters, torn down when we're done, cheap enough to recreate that
there's no reason to keep one running when we're not using it.

## Related

- [[06-containers-and-docker]]
- [[08-terraform-and-iac]] — Terraform provisions the *real* cluster (AWS EKS) that `kind`
  stands in for locally.
- A dedicated Helm doc lands when we actually write a chart in Phase 2 — for now it's just
  installed and unused.
