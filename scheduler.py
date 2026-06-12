import schedule, time
from graph import run_digest
from deliver import send_digest

def morning_run():
    print("Starting daily digest...")
    send_digest(run_digest())
    print("Done.")

schedule.every().day.at("07:00").do(morning_run)

if __name__ == "__main__":
    morning_run()          # run immediately on startup
    while True:
        schedule.run_pending()
        time.sleep(60)
