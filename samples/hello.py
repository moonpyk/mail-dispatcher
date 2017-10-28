import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def main(mail_from, subject, message):
    print("Mail : {0} '{1}' -> {1}".format(mail_from, subject, message))

    msg = MIMEMultipart()
    msg['Subject'] = "Coucou"
    msg['From'] = 'rpi-controle-lr@home.moonpyk.net'
    msg.attach(MIMEText("Coucou {0}, le sujet etait '{1}' !".format(mail_from, subject)))

    client = smtplib.SMTP('192.168.1.254')
    client.sendmail('rpi-controle-lr@home.moonpyk.net', [mail_from], msg.as_string())


if __name__ == '__main__':
    main(
        os.getenv('MD_FROM'),
        os.getenv('MD_SUBJECT'),
        os.getenv('MD_MESSAGE')
    )
