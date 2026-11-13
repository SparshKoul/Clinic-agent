#!/usr/bin/env python3
"""Moves every date in clinic.db forward by whole weeks, so the data's "today" is this week.

Run once after unzipping, and again whenever the data looks old:
    python3 tools/refresh_dates.py data/clinic.db

Dates move by whole weeks, so each appointment stays on the same weekday and inside its
doctor's working days. Standard library only.
"""
import datetime as dt
import sqlite3
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/clinic.db"
    con = sqlite3.connect(path)
    old = dt.date.fromisoformat(con.execute("SELECT value FROM clinic_info WHERE key = 'data_today'").fetchone()[0])
    today = dt.date.today()
    weeks = (today - old).days // 7
    if weeks <= 0:
        print("Data is current: data_today is {}.".format(old))
        return
    shift = "+{} days".format(weeks * 7)
    park, back = "+36400 days", "-36400 days"   # 100 years in whole weeks
    with con:
        # The one-booking-per-slot index is checked row by row, so park every appointment
        # far in the future first, then bring it back to its new date.
        con.execute("UPDATE appointments SET appointment_date = date(appointment_date, ?, ?)", (shift, park))
        con.execute("UPDATE appointments SET appointment_date = date(appointment_date, ?), "
                    "created_at = datetime(created_at, ?), updated_at = datetime(updated_at, ?)", (back, shift, shift))
        con.execute("UPDATE patients SET created_at = datetime(created_at, ?)", (shift,))
        new = old + dt.timedelta(weeks=weeks)
        con.execute("UPDATE clinic_info SET value = ? WHERE key = 'data_today'", (new.isoformat(),))
    print("Moved all dates forward {} weeks. data_today is now {} (a {}).".format(weeks, new, new.strftime("%A")))


if __name__ == "__main__":
    main()
