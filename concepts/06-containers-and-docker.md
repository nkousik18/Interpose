# Containers, and what Docker actually does

## The core idea

A **container** is a way of packaging an application together with everything it needs to run
(code, runtime, libraries, config) so it behaves identically no matter what machine it runs on.
It's not a full virtual machine — it doesn't emulate hardware or boot a separate OS kernel — it
uses features of the host's own OS kernel to give a process an isolated view of the filesystem,
network, and processes, so it *feels* like a private machine while being much lighter and
faster to start than a VM.

**Docker** is the tool that made this practical and popular: it defines a standard way to
*build* a container image (a `Dockerfile`: "start from this base, copy in this code, run this
setup"), *ship* it (push/pull from a registry), and *run* it (a single command spins up an
isolated instance of that image).

## Why Interpose needs it, specifically

A few distinct reasons stack up:

1. **Local dependencies (Postgres, Redis)**: Interpose needs a real Postgres database and Redis
   instance to develop against. Rather than installing and configuring those directly on your
   Mac, we'll run them as containers — identical setup to what production would look like,
   disposable, and gone the moment we don't need them.
2. **`kind` runs Kubernetes *inside* Docker**: `kind` = "Kubernetes IN Docker." Instead of
   needing real physical/cloud machines to form a Kubernetes cluster, `kind` runs each cluster
   "node" as a Docker container on your laptop. This only works because Docker is running.
3. **Deployment artifacts**: eventually the gateway itself, and the demo MCP servers, get
   packaged as container images (that's what the Helm chart in `charts/interpose/` deploys) —
   the same image that runs in a local `kind` cluster is what would run on real AWS EKS later.

## The daemon vs. the CLI

`docker --version` worked on your machine even before we did anything — that's just the command
line *client*. `docker info` failing meant the **Docker daemon** (the actual background service
that builds and runs containers) wasn't running — the Docker Desktop app has to be open for
that. `open -a Docker` launched it. This split (a lightweight CLI talking to a background
daemon that does the real work) is a pattern that shows up again with Kubernetes: `kubectl` is
a thin client; a cluster's control plane is where the real work happens. See
[[07-what-is-kubernetes]].

## Related

- [[07-what-is-kubernetes]]
- [[05-python-envs-and-uv]]
