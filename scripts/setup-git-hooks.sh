#!/bin/bash
# Setup Git hooks for Voice Coordination System
# This script installs pre-commit and pre-push hooks

set -e

echo "🔧 Setting up Git hooks for Voice Coordination System"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "❌ Not in a Git repository. Please run from the repository root."
    exit 1
fi

# Install pre-commit if not already installed
if ! command -v pre-commit &> /dev/null; then
    echo "📦 Installing pre-commit..."
    pip install pre-commit
fi

# Install pre-commit hooks from config
echo "🔗 Installing pre-commit hooks..."
pre-commit install

# Install pre-push hook
echo "🚀 Installing pre-push hook..."
cat > .git/hooks/pre-push << 'EOF'
#!/bin/bash
# Pre-push hook for Voice Coordination System

echo "🚀 Running pre-push tests..."

# Get the directory where this script is located
HOOK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Run the pre-push test suite
if [ -f "$REPO_ROOT/scripts/pre-push-tests.sh" ]; then
    cd "$REPO_ROOT"
    bash scripts/pre-push-tests.sh
else
    echo "⚠️  Pre-push test script not found. Allowing push to continue."
    echo "Expected: $REPO_ROOT/scripts/pre-push-tests.sh"
fi
EOF

# Make pre-push hook executable
chmod +x .git/hooks/pre-push

# Create a commit-msg hook for voice coordination commit message validation
echo "📝 Installing commit-msg hook..."
cat > .git/hooks/commit-msg << 'EOF'
#!/bin/bash
# Commit message hook for Voice Coordination System

commit_regex='^(feat|fix|docs|style|refactor|test|chore|voice)(\(.+\))?: .{1,50}'
error_msg="
❌ Invalid commit message format!

Commit message should follow the pattern:
  <type>(<scope>): <description>

Types: feat, fix, docs, style, refactor, test, chore, voice
Scope: optional, e.g., (server), (client), (e2e)
Description: concise description (max 50 chars)

Examples:
  ✅ feat(server): add priority-based queue management
  ✅ fix(client): resolve websocket connection timeout
  ✅ voice(e2e): implement macOS say() integration tests
  ✅ docs: update voice coordination system README
  ✅ test: add unit tests for coordination server
"

# Check commit message format
if ! grep -qE "$commit_regex" "$1"; then
    echo "$error_msg"
    exit 1
fi

# Check for voice coordination system keywords
commit_content=$(cat "$1")
voice_keywords=("voice.coordination" "speech.queue" "agent.priority" "coordination.server")

# If modifying voice coordination files, encourage descriptive messages
git diff --cached --name-only | grep -E "(voice_coordination|claude_code_voice_hook|autoagent_voice_integration)" > /dev/null
if [ $? -eq 0 ]; then
    echo "📢 Voice coordination files modified. Great job on the voice system!"
fi
EOF

# Make commit-msg hook executable
chmod +x .git/hooks/commit-msg

# Create a simple prepare-commit-msg hook to add context
echo "💬 Installing prepare-commit-msg hook..."
cat > .git/hooks/prepare-commit-msg << 'EOF'
#!/bin/bash
# Prepare commit message hook for Voice Coordination System

# Only process if this is a regular commit (not merge, etc.)
case "$2,$3" in
  ,|template,)
    # Check if voice coordination files are being committed
    voice_files=$(git diff --cached --name-only | grep -E "(voice_coordination|claude_code_voice_hook|autoagent_voice_integration)" | head -3)
    
    if [ -n "$voice_files" ]; then
        # Add context about voice coordination changes
        echo "" >> "$1"
        echo "# Voice Coordination System Changes:" >> "$1"
        echo "$voice_files" | while read -r file; do
            echo "#   - $file" >> "$1"
        done
        echo "#" >> "$1"
        echo "# Remember to run tests: python -m pytest tests/" >> "$1"
    fi
    ;;
  *) ;;
esac
EOF

# Make prepare-commit-msg hook executable
chmod +x .git/hooks/prepare-commit-msg

# Test the pre-commit installation
echo "🧪 Testing pre-commit installation..."
pre-commit run --all-files --show-diff-on-failure || echo "⚠️  Pre-commit checks found issues. Run 'pre-commit run --all-files' to see details."

# Create a quick test script
echo "📋 Creating test runner script..."
cat > scripts/run-tests.sh << 'EOF'
#!/bin/bash
# Quick test runner for development

echo "🚀 Running Voice Coordination System Tests"

# Unit tests only (fast)
if [ "$1" == "unit" ] || [ "$1" == "fast" ]; then
    echo "🔬 Running unit tests only..."
    python -m pytest tests/test_coordination_server.py tests/test_client_hook.py -v
    exit $?
fi

# E2E tests only  
if [ "$1" == "e2e" ]; then
    echo "🎭 Running E2E tests only..."
    python -m pytest tests/test_e2e_voice_coordination.py -v -m e2e
    exit $?
fi

# All tests (default)
echo "🧪 Running all tests..."
python -m pytest tests/ -v
EOF

chmod +x scripts/run-tests.sh

echo "✅ Git hooks setup complete!"
echo ""
echo "📋 What was installed:"
echo "  ✅ Pre-commit hooks (runs on every commit)"
echo "  ✅ Pre-push hooks (runs comprehensive tests before push)" 
echo "  ✅ Commit message validation"
echo "  ✅ Commit message preparation with context"
echo ""
echo "🧪 Available test commands:"
echo "  • scripts/run-tests.sh unit     # Fast unit tests only"
echo "  • scripts/run-tests.sh e2e      # E2E tests with speech"
echo "  • scripts/run-tests.sh          # All tests"
echo "  • scripts/pre-push-tests.sh     # Full pre-push suite"
echo ""
echo "🔧 Pre-commit commands:"
echo "  • pre-commit run                # Run on staged files"
echo "  • pre-commit run --all-files    # Run on all files"
echo "  • pre-commit autoupdate         # Update hook versions"
echo ""
echo "🎉 Voice Coordination System is now ready for development!"