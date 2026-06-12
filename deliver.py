import resend, markdown as md_lib
from datetime import date
from config import RESEND_API_KEY, DIGEST_EMAIL, DIGEST_FROM

resend.api_key = RESEND_API_KEY

def send_digest(report_md: str):
    html_body = md_lib.markdown(report_md, extensions=["tables", "toc"])
    html = f"""
    <html><body style="font-family:-apple-system,sans-serif;max-width:700px;
                       margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.6">
    {html_body}
    </body></html>"""

    resend.Emails.send({
        "from":    DIGEST_FROM,
        "to":      DIGEST_EMAIL,
        "subject": f"AI Research Digest — {date.today()}",
        "html":    html
    })
    print(f"[Deliver] Sent to {DIGEST_EMAIL}")
