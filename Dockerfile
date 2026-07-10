
# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker's build cache
# (This ensures you don't re-install dependencies if only your code changes)
COPY requirements.txt .
COPY gen-ai-ac-7d02e4103f08.json .
COPY templates .
COPY .vscode .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
# (This includes your app.py, templates folder, etc.)
COPY . .

# Expose the port your Flask app runs on
EXPOSE 5000

# Run the application
CMD ["python", "agent.py"]
