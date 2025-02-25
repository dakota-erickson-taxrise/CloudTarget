# **Real Time Transcription Creation and Analyzing**

## **1. Project Overview**

### **Overview**

This project runs in the clud and receives audio data from a program running locally on people's machines that captures mic/speaker audio. It forwards that data to AssebmlyAI to create a real
time transcript of the conversation. This transcript is then processed/analyzed for conversation landmarks and proposed responses based on what is being said. 

**Goals:**

- Goal 1: Help people understand what is remaining to be achieved within a phone call
- Goal 2: Provide responses if there is pushback

**Tech Stack:**

|Technology|Purpose|
|---|---|
|Python|Backend runtime|


## **2. Development Milestones**

This section tracks **development milestones and related tasks**. Most of the milestones for this project are still TBD. I'll leave what is pre-populated here as placeholders until milestone are better defined for this project. 

### **Milestone 1: Project Setup**

- [ ]  **Initialize Repository and CI/CD**
    - ✅  Set up Git repository
    - [ ]  Add ECR Registry
    - [ ]  Configure Flux CD
    - [ ]  Configure Docker Image
    - [ ]  Configure Bitbucket Pipelines
- [ ]  **Define Architecture**
    - [ ]  Create initial project structure
    - [ ]  Define database schema
    - [ ]  Set up configuration management

### **Milestone 2: Core Feature Development**

- [ ]  **User Authentication**
    - [ ]  Implement JWT-based authentication
    - [ ]  Set up user registration & login
    - [ ]  Hash passwords securely
- [ ]  **Database and API Setup**
    - [ ]  Design database schema
    - [ ]  Implement CRUD operations
    - [ ]  Secure API endpoints
- [ ]  **Frontend Development**
    - [ ]  Set up React project structure
    - [ ]  Build authentication UI
    - [ ]  Integrate API with frontend

### **Milestone 3: Testing & Bug Fixing**

- [ ]  **Bug Fixing**
    - [ ]  Identify and resolve critical issues
    - [ ]  Optimize performance

### **Milestone 4: Deployment & Monitoring**

- [ ]  **Deployment**
    - [ ]  Set up production environment
    - [ ]  Deploy initial version to production
- [ ]  **Monitoring & Logging**
    - [ ]  Integrate logging tools
    - [ ]  Set up Sentry

## **3. Features & Status**

Each feature includes a description, status, and a relevant code snippet.

|Feature|Status|Notes|
|---|---|---|
|Websocket set up to receive audio data| Completed|The program runs in a docker container and exposes port 8765 to receive websocket connections|
|Transcript creation|Completed|The program receives audio data and forwards that data to AssemblyAI and receives back the text of the conversation which it then writes to a file|
|Analysis|In Progress|The created transcript will then be sent for analysis along with a prompt to guage for conversation milestones and provide suggested responses|
|Storing conversation progress|Pending|This program needs to have some way of storing and identifying calls and transcripts so a front end would be able to query for a specific call and receive that information|

### **User Authentication**

**Description**: I'm not sure at the moment that user authentication is something that will need to be done. I'll revisit this after more of the back end functionality is defined/implemented.

**Implementation Details**:

- Password hashing using bcrypt.
- JWT for session management.

**Example Code:**
```python
from passlib.hash import bcrypt

def hash_password(password: str):
    return bcrypt.hash(password)

hashed_password = hash_password("user_password")
```

### **Dashboard**

**Description**: There will need to be a FE for this project so users can see the conversation progress / suggested responses in real time. Dustin has said that there were people working on a design for it previously.  
**Implementation Details**:

- React-based dashboard.
- API calls to fetch user information.

**Example Code:**

```jsx
import React from 'react';

const Dashboard = () => {
   return (
      <div>
         <h1>User Dashboard</h1>
         {/* More dashboard code here */}
      </div>
   );
};
export default Dashboard;
```

## **4. Dependencies**

### **External Dependencies**
(The only for sure dependency here as of now is Python for the backend runtime. React will likely be used for the FE, but that is not something that has been started yet. As far as Databricks / FastAPI, they are not in use at this moment, but could be utilized to finish some of the remaining BE work.)

|Package|Purpose|
|---|---|
|Python|Backend runtime|
|React.js|Frontend|
|Databricks|Database|
|FastAPI|Backend API|

### **Internal Dependencies**

|Service|Description|
|---|---|

## **5. Quick Start**

### **Prerequisites**

- Python 3.8 or above

### **Setup Steps**

#### 1. Clone Repository
```bash
git clone https://github.com/dakota-erickson-taxrise/CloudTarget && cd CloudTarget
```
#### 2. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Set Up Environment Variables
```bash
cp .env.example .env
nano .env  # Edit with your credentials
```

#### 4. Run Project
```bash
python main.py
```

## **6. Development Workflow**

### **Branching and Jira Ticket Integration**

- Use the **Jira ticket number** in both the branch name and commit messages.
- Follow the format:
    - **Branch Naming:** feature/JIRA-123-feature-name
    - **Commit Message:** JIRA-123: Implemented feature X

#### 1. Create a new feature branch
```bash
git checkout -b feature/JIRA-123-user-auth
```

#### 2. Commit changes with Jira ticket reference
```bash
git commit -m "JIRA-123: Added user authentication logic"
```

#### 3. Push changes
```bash
git push origin feature/JIRA-123-user-auth
```

#### 4. Open a pull request referencing the Jira ticket
- Open a pull request referencing the Jira ticket.
- Merge into main after approval.

### **Testing**

- Run unit tests using pytest:

```bash
pytest
```

### **Deployment Process**

1. Ensure all changes are committed and pushed.
2. Create a pull request for review.
3. Merge changes into the main branch.
4. The CI/CD pipeline automatically deploys the changes.
5. Monitor logs for errors.

---

## **7. Deployment & Monitoring**

|Environment|URL|Notes|
|---|---|---|
|Development|http://localhost:8000|Local testing|
|Staging|https://staging.yourproject.com|Pre-production environment|
|Production|https://yourproject.com|Live version|

### **Monitoring Tools**

- Logs
- Health Check: /health
- Error Reporting: Sentry

## **8. CI/CD Pipeline Configuration**

This project utilizes Bitbucket Pipelines for continuous integration and deployment. The pipeline is configured to build and deploy Docker images for both the frontend and backend services.

### Pipeline Structure

- **Backend Service:**
     - Trigger: Changes detected in the `backend/` directory.
     - Actions: Builds a Docker image and pushes it to AWS ECR under the repository `${ECR_REPOSITORY_BASE}-backend`.

- **Frontend Service:**
     - Trigger: Changes detected in the `frontend/` directory.
     - Actions: Builds a Docker image and pushes it to AWS ECR under the repository `${ECR_REPOSITORY_BASE}-frontend`.

### Environment Variables

The pipeline relies on the following environment variable:

- `ECR_REPOSITORY_BASE`: The base URL for your AWS ECR repositories. This should be set in the repository or workspace variables in Bitbucket.

### Setting Up Environment Variables in Bitbucket

1. Navigate to **Repository settings** > **Pipelines** > **Repository variables**.
2. Click **Add variable**.
3. Add the following:
     - **Name**: `ECR_REPOSITORY_BASE`
     - **Value**: `123456789012.dkr.ecr.us-west-1.amazonaws.com/project`
     - **Secured**: Enable this to keep the value hidden in logs.
4. Click **Add** to save the variable.

Ensure that the AWS credentials (`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`) with appropriate permissions are also set as repository or workspace variables to allow the pipeline to authenticate with AWS ECR.