# GitHub Setup Instructions

Your Git repository is now initialized and ready to be pushed to GitHub! Follow these steps to create a GitHub repository and push your code.

## Step 1: Create a GitHub Repository

### Option A: Using GitHub Web Interface (Recommended for beginners)

1. Go to https://github.com and log in to your account
2. Click the "+" icon in the top right corner
3. Select "New repository"
4. Fill in the repository details:
   - **Repository name**: `hierarchical-classifier-api` (or your preferred name)
   - **Description**: "Hierarchical text classification API using sentence transformers and PyTorch"
   - **Visibility**: Choose Public or Private
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
5. Click "Create repository"

### Option B: Using GitHub CLI

```bash
# Install GitHub CLI if you haven't already
# macOS: brew install gh
# Linux: https://github.com/cli/cli#installation

# Authenticate
gh auth login

# Create repository
gh repo create hierarchical-classifier-api --public --source=. --remote=origin
```

## Step 2: Push Your Code to GitHub

After creating the repository on GitHub, you'll see instructions. Use these commands:

### If you created the repo via Web Interface:

```bash
cd /Users/kazybek.kassym/Desktop/DAF/Прокуратура/project00

# Add the remote repository (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/hierarchical-classifier-api.git

# Verify the remote was added
git remote -v

# Push your code to GitHub
git branch -M main
git push -u origin main
```

### If you used GitHub CLI:

```bash
cd /Users/kazybek.kassym/Desktop/DAF/Прокуратура/project00

# The remote is already configured, just push
git push -u origin main
```

## Step 3: Verify the Upload

1. Go to your repository page on GitHub
2. You should see all your files including:
   - README.md
   - Dockerfile
   - docker-compose.yml
   - hier_flask_api.py
   - artifacts_best_gpu/
   - And all other files

## Step 4: Add Repository Details to README (Optional)

Update the README.md with your actual repository URL:

```bash
# Edit README.md and replace <your-repo-url> with actual URL
# Then commit and push:
git add README.md
git commit -m "Update repository URL in README"
git push
```

## Step 5: Test Cloning (Recommended)

Test that others can clone and use your repository:

```bash
# In a different directory, try cloning
cd /tmp
git clone https://github.com/YOUR_USERNAME/hierarchical-classifier-api.git
cd hierarchical-classifier-api

# Build and run with Docker
docker compose up --build
```

## Common Issues and Solutions

### Issue: "Permission denied (publickey)"

**Solution**: You need to set up SSH keys or use HTTPS with credentials.

For HTTPS with personal access token:
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate a new token with `repo` scope
3. Use the token as your password when pushing

For SSH:
```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Copy public key and add to GitHub
cat ~/.ssh/id_ed25519.pub
# Go to GitHub Settings → SSH and GPG keys → New SSH key
```

### Issue: "Updates were rejected because the remote contains work..."

**Solution**: You selected options that initialized the repo with files. Either:
- Delete the remote repo and create a new empty one, OR
- Pull first: `git pull origin main --allow-unrelated-histories`

### Issue: Large files warning

The `artifacts_best_gpu/` folder contains model files that might be large. If you encounter size limits:

**Solution 1**: Use Git LFS (Large File Storage)
```bash
# Install Git LFS
git lfs install

# Track large files
git lfs track "*.joblib"
git lfs track "*.safetensors"

# Add and commit the .gitattributes file
git add .gitattributes
git commit -m "Add Git LFS tracking"
git push
```

**Solution 2**: Exclude artifacts from Git
```bash
# Add to .gitignore
echo "artifacts_best_gpu/" >> .gitignore

# Remove from Git (keeps local files)
git rm -r --cached artifacts_best_gpu/
git commit -m "Remove large artifacts from Git"
git push

# Add download instructions to README for users to obtain artifacts separately
```

## Recommended GitHub Repository Settings

### Branch Protection (for collaborative work)

1. Go to repository Settings → Branches
2. Add rule for `main` branch
3. Enable:
   - Require pull request reviews before merging
   - Require status checks to pass before merging

### Add Topics

Add relevant topics to make your repository discoverable:
- `machine-learning`
- `nlp`
- `text-classification`
- `pytorch`
- `sentence-transformers`
- `flask-api`
- `docker`
- `hierarchical-classification`

### Create Releases

When you reach a stable version:

```bash
# Tag your release
git tag -a v1.0.0 -m "Initial release"
git push origin v1.0.0
```

Then create a release on GitHub with release notes.

## Next Steps

1. ✅ Repository created and code pushed
2. 📝 Update README.md with actual repository URL
3. 🏷️ Add topics to repository
4. 📦 Consider using Git LFS if artifact files are large
5. 📄 Add a LICENSE file if not already present
6. 🔄 Set up CI/CD (optional, see CICD_SETUP.md)
7. 📊 Add badges to README for build status, Docker pulls, etc.

## Sharing with Team Members

Once your repository is on GitHub, team members can easily use it:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/hierarchical-classifier-api.git
cd hierarchical-classifier-api

# Run with Docker
docker compose up -d

# Test the API
python test_api.py
```

## Support

If you encounter issues:
1. Check GitHub's documentation: https://docs.github.com
2. GitHub CLI documentation: https://cli.github.com/manual/
3. Git documentation: https://git-scm.com/doc

