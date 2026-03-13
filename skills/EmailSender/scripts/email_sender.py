import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_HOST = "smtp.example.com"
EMAIL_PORT = 587
EMAIL_USER = "your_email@example.com"
EMAIL_PASSWORD = "your_password"
EMAIL_FROM = EMAIL_USER
EMAIL_TO = ["recipient1@example.com", "recipient2@example.com"]

subjects = [
    "Welcome to our service!",
    "Important update regarding your account",
    "New features available now"
]

msg = MIMEMultipart()
msg['From'] = EMAIL_FROM
msg['To'] = ", ".join(EMAIL_TO)
msg['Subject'] = subjects[0]

body = "This is the first email.\n\nRegards,\nYour Service"
msg.attach(MIMEText(body, 'plain'))

server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
server.starttls()
server.login(EMAIL_USER, EMAIL_PASSWORD)
text = msg.as_string()
server.sendmail(EMAIL_FROM, EMAIL_TO, text)
server.quit()

print("Email sent successfully.")

for subject in subjects[1:]:
    msg['Subject'] = subject
    body = f"This is a new email with the subject {subject}.\n\nRegards,\nYour Service"
    msg.attach(MIMEText(body, 'plain'))
    text = msg.as_string()
    server.sendmail(EMAIL_FROM, EMAIL_TO, text)

print("All emails have been sent.")