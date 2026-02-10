# CI/CD Documentation Index

This index provides an overview of all CI/CD and deployment documentation for SimBoard.

---

## 📚 Documentation Overview

| Document | Purpose | Audience | Size |
|----------|---------|----------|------|
| [QUICKSTART_CICD.md](QUICKSTART_CICD.md) | Quick setup guide | Admins & DevOps | 7 KB |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Comprehensive deployment guide | Everyone | 13.8 KB |
| [GITHUB_SECRETS.md](GITHUB_SECRETS.md) | GitHub Secrets configuration | Admins | 4.1 KB |
| [CI_CD_REFERENCE.md](CI_CD_REFERENCE.md) | Workflow quick reference | Developers | 7 KB |
| [CI_CD_IMPLEMENTATION_SUMMARY.md](CI_CD_IMPLEMENTATION_SUMMARY.md) | Implementation details | Maintainers | 9.2 KB |

**Total Documentation:** 41 KB across 5 documents

---

## 🎯 Where to Start

### I'm a Repository Administrator
**Goal:** Set up GitHub Secrets and enable CI/CD

👉 Start here: [QUICKSTART_CICD.md](QUICKSTART_CICD.md) (Steps 1-4)

Then: [GITHUB_SECRETS.md](GITHUB_SECRETS.md) for detailed setup

---

### I'm a DevOps Engineer
**Goal:** Deploy containers to NERSC Spin

👉 Start here: [QUICKSTART_CICD.md](QUICKSTART_CICD.md) (Steps 5-6)

Then: [DEPLOYMENT.md](DEPLOYMENT.md) for full deployment guide

---

### I'm a Developer
**Goal:** Understand how to trigger builds and cut releases

👉 Start here: [CI_CD_REFERENCE.md](CI_CD_REFERENCE.md) for workflow overview

Then: [DEPLOYMENT.md](DEPLOYMENT.md) → [Production Release Process](#production-release-process)

---

### I'm a Maintainer
**Goal:** Understand implementation details and architecture

👉 Start here: [CI_CD_IMPLEMENTATION_SUMMARY.md](CI_CD_IMPLEMENTATION_SUMMARY.md)

Then: [DEPLOYMENT.md](DEPLOYMENT.md) for complete reference

---

## 📖 Document Descriptions

### [QUICKSTART_CICD.md](QUICKSTART_CICD.md)
**Quick Start: CI/CD Setup**

Step-by-step guide to:
- Configure GitHub Secrets (5 min)
- Test dev backend builds (5 min)
- Update NERSC Spin deployments (10 min)
- Cut a test release (10 min)

**When to use:** First-time setup or onboarding new team members

---

### [DEPLOYMENT.md](DEPLOYMENT.md)
**Comprehensive Deployment Guide**

Complete reference covering:
- Environment architecture (dev vs prod)
- CI/CD workflow details
- Image naming and tagging conventions
- Production release process (step-by-step)
- Kubernetes deployment examples
- Troubleshooting guide

**When to use:** 
- Reference for release process
- Troubleshooting deployment issues
- Understanding the full system

---

### [GITHUB_SECRETS.md](GITHUB_SECRETS.md)
**GitHub Secrets Configuration**

Detailed guide for:
- Required secrets list
- Step-by-step configuration
- Testing and verification
- Troubleshooting auth issues
- Security best practices

**When to use:**
- Setting up GitHub Secrets
- Rotating credentials
- Debugging authentication failures

---

### [CI_CD_REFERENCE.md](CI_CD_REFERENCE.md)
**Workflow Quick Reference**

Quick reference for:
- Workflow overview table
- Trigger conditions
- Manual dispatch instructions
- Common operations
- Monitoring and troubleshooting

**When to use:**
- Quick lookup for workflow info
- Understanding trigger conditions
- Finding workflow commands

---

### [CI_CD_IMPLEMENTATION_SUMMARY.md](CI_CD_IMPLEMENTATION_SUMMARY.md)
**Implementation Details**

Technical documentation covering:
- What was implemented
- Architecture decisions and rationale
- Image tagging strategy
- Required setup
- Success criteria and next steps

**When to use:**
- Understanding implementation choices
- Reviewing architecture decisions
- Planning future enhancements

---

## 🔄 Common Workflows

### First-Time Setup
```
1. QUICKSTART_CICD.md (Steps 1-4) → Configure secrets & test
2. GITHUB_SECRETS.md → Verify configuration
3. QUICKSTART_CICD.md (Steps 5-6) → Deploy to NERSC
4. CI_CD_REFERENCE.md → Understand workflows
```

### Cutting a Release
```
1. CI_CD_REFERENCE.md → Review workflow overview
2. DEPLOYMENT.md → Production Release Process section
3. QUICKSTART_CICD.md (Step 8) → Optional test release first
```

### Troubleshooting
```
1. CI_CD_REFERENCE.md → Troubleshooting section
2. DEPLOYMENT.md → Troubleshooting section
3. GITHUB_SECRETS.md → Auth troubleshooting
```

### Onboarding New Team Members
```
1. CI_CD_IMPLEMENTATION_SUMMARY.md → Understand the system
2. CI_CD_REFERENCE.md → Learn workflows
3. QUICKSTART_CICD.md → Hands-on practice
```

---

## 🚀 CI/CD Pipeline Overview

```mermaid
graph LR
    A[Push to main] --> B[Backend CI]
    A --> C[Build Backend Dev]
    C --> D[registry.nersc.gov<br/>backend:dev]
    D --> E[NERSC Spin Dev]
    
    F[Create Release v0.3.0] --> G[Build Backend Prod]
    F --> H[Build Frontend Prod]
    G --> I[registry.nersc.gov<br/>backend:v0.3.0]
    H --> J[registry.nersc.gov<br/>frontend:v0.3.0]
    I --> K[NERSC Spin Prod]
    J --> K
```

---

## 📝 Workflow Files

Located in `.github/workflows/`:

- `backend-ci.yml` - Run tests and linting on backend changes
- `build-backend-dev.yml` - Build dev backend on `main` push
- `build-backend-prod.yml` - Build prod backend on releases/tags
- `build-frontend-prod.yml` - Build prod frontend on releases/tags

---

## 🔗 External Resources

- [NERSC Container Registry](https://docs.nersc.gov/development/containers/registry/)
- [NERSC Spin Documentation](https://docs.nersc.gov/services/spin/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Buildx Documentation](https://docs.docker.com/buildx/working-with-buildx/)
- [Semantic Versioning](https://semver.org/)

---

## 📞 Support

For questions or issues:

1. **Check documentation** in this index
2. **Review workflow logs** in GitHub Actions
3. **Consult troubleshooting sections** in relevant docs
4. **Open an issue**: [GitHub Issues](https://github.com/E3SM-Project/simboard/issues)
5. **Contact**: E3SM DevOps Team

---

## 🔄 Keeping Documentation Updated

This documentation should be updated when:
- CI/CD workflows change
- Deployment process changes
- New environments are added
- Troubleshooting patterns emerge
- Team onboarding reveals gaps

**Last Updated:** 2026-02-10
