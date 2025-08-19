## Python environment
python3 -m venv .venv
source .venv/bin/activate

brew update && brew install azure-cli 
pip install openai azure-ai-projects azure-identity

## Deploy to Azure
func azure functionapp publish the-globe-function