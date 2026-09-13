VM_IP := $(shell cd opentofu/proxmox-vm && tofu output -raw vm_ip_address 2>/dev/null)
API_VERSION ?= v1
SSH := ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@$(VM_IP)

.PHONY: init plan apply destroy bootstrap build-api deploy-apps argocd-password reset-cluster

init:
	cd opentofu/proxmox-vm && tofu init

plan:
	cd opentofu/proxmox-vm && tofu plan

apply:
	cd opentofu/proxmox-vm && tofu apply

destroy:
	cd opentofu/proxmox-vm && tofu destroy

bootstrap:
	cd ansible && ansible-playbook playbooks/site.yml

build-api:
	tar -C apps/shipping-cost-api -cf - . | $(SSH) "mkdir -p ~/wab-api && tar -xf - -C ~/wab-api"
	$(SSH) "cd ~/wab-api && sudo podman build -t localhost/shipping-cost-api:$(API_VERSION) . && sudo podman save -o /tmp/shipping-cost-api.tar localhost/shipping-cost-api:$(API_VERSION) && sudo env KIND_EXPERIMENTAL_PROVIDER=podman kind load image-archive /tmp/shipping-cost-api.tar --name wab && sudo rm -f /tmp/shipping-cost-api.tar"

deploy-apps:
	kubectl --kubeconfig ansible/kubeconfig apply -f apps/applications

argocd-password:
	@kubectl --kubeconfig ansible/kubeconfig --namespace argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo

reset-cluster:
	$(SSH) "sudo kind delete clusters --name wab && sudo rm -f /root/.kube/config"
	$(MAKE) bootstrap
