import re

RE_EMAIL_SUBJECT = r'^Subject: (.*)$'
RE_EMAIL_BODY = r'^(.*)$\n(.*)'

def find_subject(email):
    match = re.search(RE_EMAIL_SUBJECT, email)
    if match:
        return match.group(1)
    return None

def find_body(email):
    match = re.search(RE_Email_BODY, email)
    if match:
        return match.group(2)
    return None

def respond_to_subject(subject):
    responses = {
        "Meeting Request": "Thank you for the meeting request. I will check my schedule and get back to you soon.",
        "Follow Up": "I appreciate your follow-up. Let's discuss further at a convenient time.",
        "Job Application": "Thank you for applying to our company. We will review your application and get back to you within a week.",
    }

    if subject in responses:
        return responses[subject]
    return f"I'm sorry, I don't have a response for the subject '{subject}'."

def main():
    with open("emails.txt", "r") as file:
        emails = file.readlines()

    for email in emails:
        subject = find_subject(email)
        if subject:
            body = find_body(email)
            response = respond_to_subject(subject)
            print(f"Subject: {subject}")
            print(f"{response}\n")
            if body:
                print(f"{body}")

if __name__ == "__main__":
    main()