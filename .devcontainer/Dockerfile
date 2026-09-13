FROM quay.io/fedora/fedora:46

RUN dnf -y install \
        git \
        make \
        curl \
        jq \
        openssh-clients \
        ansible-core \
    && dnf clean all

RUN useradd -u 1000 -ms /bin/bash vscode \
    && mkdir -p /home/vscode/.config/opencode /home/vscode/.local/share/opencode \
    && chown -R vscode:vscode /home/vscode

ARG GO_VERSION=1.27.0
ARG KUBECTL_VERSION=1.37.0
ARG KUSTOMIZE_VERSION=5.5.0
ARG OPENTOFU_VERSION=1.12.6
ARG ARGOCD_VERSION=3.0.3
ARG K6_VERSION=0.57.0
ARG OPENCODE_VERSION=1.18.30

RUN set -e; \
    case "$(uname -m)" in \
        x86_64)  k=amd64; oc=x64   ;; \
        aarch64) k=arm64;  oc=arm64 ;; \
    esac; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${k}.tar.gz" | tar -xz -C /usr/local; \
    curl -fsSL "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${k}/kubectl" -o /usr/local/bin/kubectl; \
    curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE_VERSION}/kustomize_v${KUSTOMIZE_VERSION}_linux_${k}.tar.gz" | tar -xz -C /usr/local/bin kustomize; \
    curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_linux_${k}.tar.gz" | tar -xz -C /usr/local/bin tofu; \
    curl -fsSL "https://github.com/argoproj/argo-cd/releases/download/v${ARGOCD_VERSION}/argocd-linux-${k}" -o /usr/local/bin/argocd; \
    curl -fsSL "https://github.com/grafana/k6/releases/download/v${K6_VERSION}/k6-v${K6_VERSION}-linux-${k}.tar.gz" | tar -xz -C /tmp; \
    mv "/tmp/k6-v${K6_VERSION}-linux-${k}/k6" /usr/local/bin/k6 && rm -rf "/tmp/k6-v${K6_VERSION}-linux-${k}"; \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${oc}.tar.gz" | tar -xz -C /usr/local/bin opencode; \
    chmod +x /usr/local/bin/kubectl /usr/local/bin/kustomize /usr/local/bin/tofu /usr/local/bin/argocd /usr/local/bin/k6 /usr/local/bin/opencode

ENV PATH=/usr/local/go/bin:${PATH}
