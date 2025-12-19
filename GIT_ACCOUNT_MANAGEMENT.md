# Git Account Management Guide

> How to manage personal vs. work GitHub accounts and ensure commits go to the right place

**Author:** Jordan Cheung  
**Date:** Dec 18, 2024

---

## 🎯 The Problem

You have:
- **Personal GitHub:** `jcheung611@gmail.com` (jcheung611-byte)
- **Work GitHub:** `jordan.cheung@doordash.com` (jordan-cheung-dd)

You want to ensure:
- Personal projects commit with personal email
- Work projects commit with work email
- Each pushes to the correct GitHub account

---

## ✅ The Solution: Per-Repo Configuration

### **Key Principle:**

**Global config** = Default for all repos  
**Local config** = Overrides for specific repo

```bash
# Check global config (your default)
git config --global user.name
git config --global user.email

# Check local config (this repo only)
git config user.name
git config user.email
```

---

## 🔧 Setting Up a New Personal Project

### **Option 1: Quick Setup Script**

Save this as `setup-personal-repo.sh` in your home directory:

```bash
#!/bin/bash
# Usage: ./setup-personal-repo.sh

echo "🎯 Setting up personal Git repo..."

# Set personal identity for THIS repo only
git config user.name "Jordan Cheung"
git config user.email "jcheung611@gmail.com"

# Verify
echo ""
echo "✅ Local repo config:"
echo "   Name: $(git config user.name)"
echo "   Email: $(git config user.email)"
echo ""
echo "🔍 Global config (unchanged):"
echo "   Name: $(git config --global user.name)"
echo "   Email: $(git config --global user.email)"
```

**Usage:**
```bash
cd /path/to/your/new/project
chmod +x ~/setup-personal-repo.sh
~/setup-personal-repo.sh
```

---

### **Option 2: Manual Setup**

```bash
cd /path/to/your/personal/project

# Set local config for this repo
git config user.name "Jordan Cheung"
git config user.email "jcheung611@gmail.com"

# Verify
git config user.email  # Should show: jcheung611@gmail.com
```

---

## 🏢 Setting Up a New Work Project

### **Option 1: Keep Global Config as Work**

If most of your projects are work:

```bash
# Set global to work
git config --global user.name "jordan-cheung-dd"
git config --global user.email "jordan.cheung@doordash.com"

# Then for personal projects, use local override (see above)
```

### **Option 2: Use Directory-Based Config**

Git supports conditional config based on directory!

**Edit `~/.gitconfig`:**

```ini
[user]
    name = jordan-cheung-dd
    email = jordan.cheung@doordash.com

# Personal projects in this directory
[includeIf "gitdir:~/Documents/GitHub/Personal/"]
    path = ~/.gitconfig-personal

# Work projects in this directory
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig-work
```

**Create `~/.gitconfig-personal`:**

```ini
[user]
    name = Jordan Cheung
    email = jcheung611@gmail.com
```

**Create `~/.gitconfig-work`:**

```ini
[user]
    name = jordan-cheung-dd
    email = jordan.cheung@doordash.com
```

**Now:**
- Any repo in `~/Documents/GitHub/Personal/` → Automatically uses personal email!
- Any repo in `~/work/` → Automatically uses work email!

**This is the BEST solution!** ✨

---

## 🔐 GitHub Authentication (GitHub CLI)

### **Current Setup:**

```bash
gh auth status
# Shows: ✓ Logged in to github.com as jcheung611-byte
```

### **To Add Work Account:**

GitHub CLI can manage multiple accounts:

```bash
# Login to work account
gh auth login

# Select:
# - GitHub.com
# - HTTPS
# - Authenticate with browser
# - Login with work credentials

# Now you can switch between accounts
gh auth switch
```

### **To Check Which Account is Active:**

```bash
gh auth status
```

### **Pro Tip: Automatic Account Selection**

GitHub CLI automatically uses the right account based on the repo's remote URL:

- `https://github.com/jcheung611-byte/*` → Personal account
- `https://github.com/doordash/*` → Work account (if logged in)

---

## 📋 Pre-Commit Checklist Template

Before your first commit on any project:

```bash
# 1. Check author identity
git config user.email
# ✅ Expected: jcheung611@gmail.com (personal) or jordan.cheung@doordash.com (work)

# 2. Check remote URL
git remote -v
# ✅ Expected: github.com/jcheung611-byte/* (personal) or github.com/doordash/* (work)

# 3. Check GitHub CLI authentication
gh auth status
# ✅ Expected: Logged in as correct account

# 4. Verify .gitignore exists
ls -la .gitignore
# ✅ Expected: File exists and excludes .env, secrets, etc.

# 5. Make initial commit
git add -A
git commit -m "Initial commit: [description]"

# 6. Verify commit author BEFORE pushing
git log -1 --pretty=format:"Author: %an <%ae>"
# ✅ Expected: Correct name and email

# 7. Push to GitHub
git push -u origin main
```

---

## 🚨 Common Mistakes & Fixes

### **Mistake 1: Committed with Wrong Email**

**Fix BEFORE pushing:**

```bash
# Amend last commit with correct author
git commit --amend --reset-author --no-edit

# Verify
git log -1 --pretty=format:"Author: %an <%ae>"
```

**Fix AFTER pushing (requires force push):**

```bash
# ⚠️ Only do this if you're the only one working on the repo!
git commit --amend --reset-author --no-edit
git push --force
```

---

### **Mistake 2: Pushing to Wrong Remote**

**Check before pushing:**

```bash
git remote -v
# origin  https://github.com/WRONG-ACCOUNT/repo.git (fetch)
```

**Fix:**

```bash
git remote set-url origin https://github.com/CORRECT-ACCOUNT/repo.git
git remote -v  # Verify
git push -u origin main
```

---

### **Mistake 3: .env File Got Committed**

**Remove from Git history:**

```bash
# Add to .gitignore
echo ".env" >> .gitignore

# Remove from Git (but keep local file)
git rm --cached .env

# Commit the removal
git commit -m "Remove .env from tracking"

# Push
git push
```

**If already pushed and contains secrets:**

```bash
# ⚠️ ROTATE YOUR SECRETS FIRST! (API keys, passwords, etc.)

# Remove from history (requires force push)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (⚠️ DANGEROUS if others are using the repo)
git push --force --all
```

---

## 📝 New Project Setup Template

### **Personal Project Checklist:**

```bash
# 1. Create project directory
mkdir -p ~/Documents/GitHub/Personal/my-new-project
cd ~/Documents/GitHub/Personal/my-new-project

# 2. Initialize Git
git init

# 3. Set local identity (if not using directory-based config)
git config user.name "Jordan Cheung"
git config user.email "jcheung611@gmail.com"

# 4. Create .gitignore
cat > .gitignore << 'EOF'
# Environment
.env
*.env

# Python
__pycache__/
*.py[cod]
venv/
.venv/

# IDE
.vscode/
.idea/
.DS_Store

# Output/Data
output/
data/*.csv
*.log
EOF

# 5. Create .env.example (template for others)
cat > .env.example << 'EOF'
# API Keys
OPENAI_API_KEY=your_key_here
EOF

# 6. Create README
cat > README.md << 'EOF'
# My New Project

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your keys
3. Run: `python main.py`
EOF

# 7. Initial commit
git add -A
git commit -m "Initial commit: Project setup"

# 8. Verify author BEFORE pushing
git log -1 --pretty=format:"Author: %an <%ae>"
# Should show: Jordan Cheung <jcheung611@gmail.com>

# 9. Create GitHub repo (via CLI or web)
gh repo create my-new-project --public --source=. --remote=origin

# 10. Push
git push -u origin main
```

---

## 🎓 Best Practices Summary

### **DO:**

✅ Set local `user.email` for each personal project (or use directory-based config)  
✅ Add `.gitignore` BEFORE first commit  
✅ Create `.env.example` for templates, never commit `.env`  
✅ Verify author with `git log -1` BEFORE pushing  
✅ Use descriptive commit messages  
✅ Keep work and personal projects in separate directories

### **DON'T:**

❌ Assume global config is correct - always verify!  
❌ Commit secrets, API keys, or credentials  
❌ Force push to shared/team repos  
❌ Skip the pre-commit checklist  
❌ Use `git add .` without checking what's being staged

---

## 🔍 Quick Reference Commands

```bash
# Check current identity
git config user.email

# Check global identity
git config --global user.email

# Set personal (local)
git config user.email "jcheung611@gmail.com"

# Set work (local)
git config user.email "jordan.cheung@doordash.com"

# Verify last commit author
git log -1 --pretty=format:"Author: %an <%ae>"

# Check remote URL
git remote -v

# Check GitHub CLI status
gh auth status

# View staged files before commit
git status
git diff --staged

# Undo staged files
git reset HEAD <file>

# Undo last commit (keep changes)
git reset HEAD~1
```

---

## 📚 Additional Resources

- [Git Config Documentation](https://git-scm.com/docs/git-config)
- [GitHub CLI Manual](https://cli.github.com/manual/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [.gitignore Templates](https://github.com/github/gitignore)

---

**Last Updated:** Dec 18, 2024  
**Maintained By:** Jordan Cheung

**For future reference:** Keep this guide in `~/Documents/git-account-guide.md` or at the root of any personal project.

