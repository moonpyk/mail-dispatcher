# coding=utf-8
from __future__ import print_function

import email
import imaplib
import os
import smtplib
import subprocess
import sys
from ConfigParser import *
from cgi import escape
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

LOOKUP_TABLE = [
    "./mail-dispatch.conf",
    "~/mail-dispatch.conf",
    "/etc/mail-dispatch.conf"
]

ERROR_CODES = {
    'ERR_CONFIG': 1,
}

DELETE = True


def main():
    cfg = open_config()

    try:
        host = cfg.get('Configuration', 'imap_server')

        if cfg.has_option('Configuration', 'imap_ssl') and cfg.getboolean('Configuration', 'imap_ssl'):
            mail_client = imaplib.IMAP4_SSL(host=host)
        else:
            mail_client = imaplib.IMAP4(host=host)

        mail_client.login(
            cfg.get('Configuration', 'imap_user'),
            cfg.get('Configuration', 'imap_password')
        )

    except (NoSectionError, NoOptionError) as e:
        print(e, sys.stderr)
        sys.exit(ERROR_CODES['ERR_CONFIG'])

    mail_client.select()

    _, data = mail_client.search(None, 'ALL')

    avail = data[0].split()

    for mail_id in avail:
        _, mail_data = mail_client.fetch(mail_id, '(RFC822)')

        for part in mail_data:
            if isinstance(part, tuple) and handle_email(cfg, part) and DELETE:
                # Mark the mail for deletion
                mail_client.store(mail_id, '+FLAGS', '\\Deleted')

    mail_client.expunge()
    mail_client.close()


def open_config():
    cfg = ConfigParser()
    cfg.read(LOOKUP_TABLE)
    return cfg


def handle_email(cfg, mail_data):
    mail = email.message_from_string(mail_data[1])

    assert isinstance(mail, Message)

    mail_from = email.utils.parseaddr(mail.get('From'))[1]
    mail_subject = mail.get('Subject').lower().strip()
    mail_payload = None

    # noinspection PyBroadException
    try:
        raw_payload = mail.get_payload()

        if isinstance(raw_payload, str):
            mail_payload = str(raw_payload).strip()

        elif isinstance(raw_payload, list):
            for part in raw_payload:
                if isinstance(part, Message) and part.get_content_type() == 'text/plain':
                    mail_payload = str(part.get_payload(decode=True)).strip()
                    break

    except Exception as e:
        print(e, sys.stderr)
        return False

    if mail_payload is None:
        mail_payload = ''

    if len(mail_from) == 0 or len(mail_subject) == 0:
        return False

    admins = []

    if cfg.has_option('Configuration', 'admin'):
        admins = [
            i.lower().strip()
            for i in cfg.get('Configuration', 'admin').split(';')
            if len(i) > 0
        ]

    is_admin = len(mail_from) > 0 and len(admins) > 0 and mail_from in admins

    parsed_mail = {
        'from': mail_from,
        'is_admin': is_admin,
        'subject': mail_subject,
        'message': mail_payload
    }

    final_code = 0

    was_parsed = False

    for (command, syscmd) in cfg.items('Commands'):
        if mail_subject == command.lower():
            was_parsed = True
            try:
                final_code = exec_cmd(syscmd, parsed_mail)
            except Exception as e:
                final_code = -20
                print(e, sys.stderr)
            break

    if not was_parsed or final_code != 0 or not is_admin:
        # noinspection PyBroadException
        try:
            notify_admin(cfg, admins, parsed_mail, was_parsed, final_code)
        except Exception as e:
            print(e, file=sys.stderr)

    return True


def exec_cmd(syscmd, parsed):
    args = syscmd.split(' ')
    args.append(parsed['from'])
    args.append(parsed['subject'])

    new_env = os.environ.copy()
    new_env["FROM_MAIL"] = "True"
    new_env["MD_FROM"] = parsed['from']
    new_env["MD_SUBJECT"] = parsed['subject']
    new_env["MD_MESSAGE"] = parsed['message']
    new_env["MD_IS_ADMIN"] = str(parsed['is_admin'])

    return subprocess.call(args, env=new_env)


def notify_admin(cfg, admins, parsed_mail, was_parsed, final_code):
    if len(admins) == 0:
        return

    smtp_server = 'localhost'

    if cfg.has_option('Configuration', 'smtp_server'):
        smtp_server = cfg.get('Configuration', 'smtp_server')

    if len(smtp_server) == 0:
        return

    if cfg.has_option('Configuration', 'smtp_ssl') and cfg.getboolean('Configuration', 'smtp_ssl'):
        client = smtplib.SMTP_SSL(smtp_server)
    else:
        client = smtplib.SMTP(smtp_server)

    mail_vars = dict(parsed_mail)
    mail_vars['was_parsed'] = was_parsed
    mail_vars['exit_code'] = final_code

    # Escaping string values, just in case they contain HTML
    for k in mail_vars:
        if isinstance(mail_vars[k], str):
            mail_vars[k] = escape(mail_vars[k])

    content = """<html>
<head>
    <title>mail-dispatcher notification</title>
</head>
<body>
<h1>mail-dispatcher notification</h1>
<table>
    <tr>
        <td>From :</td>
        <td>{data[from]} (Admin: {data[is_admin]})</td>
    </tr>
    <tr>
        <td>Subject :</td>
        <td>{data[subject]}</td>
    </tr>
    <tr>
        <td>Message :</td>
        <td>{data[message]}</td>
    </tr>
    <tr>
        <td>Admin ? :</td>
        <td>{data[is_admin]}</td>
    </tr>
    <tr>
        <td>Parsed :</td>
        <td>{data[was_parsed]}</td>
    </tr>
    <tr>
        <td>Exit code :</td>
        <td>{data[exit_code]}</td>
    </tr>
</table>
</body>
</html>""".format(data=mail_vars)

    from_mail = cfg.get('Configuration', 'smtp_from')

    msg = MIMEMultipart()
    msg["From"] = from_mail
    msg["Subject"] = 'mail-dispatcher notification'
    msg.attach(MIMEText(content, 'html'))

    client.sendmail(
        from_mail,
        admins,
        msg.as_string()
    )
    client.quit()


if __name__ == '__main__':
    main()
