#!/usr/bin/python3

import base64
import hashlib
import os
import random
import string
import time
import uuid
import argparse
from time import sleep
from urllib.parse import urlparse
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fake_useragent import UserAgent
from future.backports.urllib.parse import parse_qs
from rich import print_json, print
from rich.console import Console

from medihunter_notifiers import telegram_notify
import sqlite3

console = Console()

# Load environment variables
load_dotenv()

class Authenticator:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = None
        self.headers = {
            "User-Agent": UserAgent().random,
            "Accept": "application/json",
            "Authorization": None
        }
        self.tokenA = None

    def generate_code_challenge(self, input):
        sha256 = hashlib.sha256(input.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(sha256).decode("utf-8").rstrip("=")

    def login(self):
        self.session = requests.Session()
        state = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
        device_id = str(uuid.uuid4())
        code_verifier = "".join(uuid.uuid4().hex for _ in range(3))
        code_challenge = self.generate_code_challenge(code_verifier)

        login_url = "https://login-online24.medicover.pl"
        oidc_redirect = "https://online24.medicover.pl/signin-oidc"
        epoch_time = int(time.time()) * 1000

        auth_params = (
            f"?client_id=web&redirect_uri={oidc_redirect}&response_type=code"
            f"&scope=openid+offline_access+profile&state={state}&code_challenge={code_challenge}"
            f"&code_challenge_method=S256&response_mode=query&ui_locales=pl&app_version=3.4.0-beta.1.0"
            f"&previous_app_version=3.4.0-beta.1.0&device_id={device_id}&device_name=Chrome&ts={epoch_time}"
        )

        # Step 1: Initialize login
        response = self.session.get(f"{login_url}/connect/authorize{auth_params}", headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 2: Extract CSRF token
        response = self.session.get(next_url, headers=self.headers, allow_redirects=False)
        soup = BeautifulSoup(response.content, "html.parser")
        csrf_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if csrf_input:
            csrf_token = csrf_input.get("value")
        else:
            raise ValueError("CSRF token not found in the login page.")

        # Step 3: Submit login form
        login_data = {
            "Input.ReturnUrl": f"/connect/authorize/callback{auth_params}",
            "Input.LoginType": "FullLogin",
            "Input.Username": self.username,
            "Input.Password": self.password,
            "Input.Button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        response = self.session.post(next_url, data=login_data, headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 4: Fetch authorization code
        response = self.session.get(f"{login_url}{next_url}", headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")
        code = parse_qs(urlparse(next_url).query)["code"][0]

        # Step 5: Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "redirect_uri": oidc_redirect,
            "code": code,
            "code_verifier": code_verifier,
            "client_id": "web",
        }
        response = self.session.post(f"{login_url}/connect/token", data=token_data, headers=self.headers)
        tokens = response.json()
        self.tokenA = tokens["access_token"]
        self.headers["Authorization"] = f"Bearer {self.tokenA}"

class DB:
    def __init__(self):
        self.conn = sqlite3.connect('db/appointments.db')
        self.cur = self.conn.cursor()
        self.cur.execute("CREATE TABLE IF NOT EXISTS watch(id integer primary key, region, speciality, clinic, doctor, date)")
        self.cur.execute("CREATE TABLE IF NOT EXISTS appointment(clinic, doctor, date)")
        self.clear_db()

    def clear_db(self):
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.cur.execute("DELETE from appointment "
                         "where date < (?)", (now,))
        now = datetime.datetime.now() - datetime.timedelta(days=14)
        now = now.strftime("%Y-%m-%d")
        self.cur.execute("DELETE from watch "
                         "where date < (?)", (now,))
        self.conn.commit()

    def appointment_exists(self, clinic, doctor, date):
        res = self.cur.execute("SELECT * from appointment "
                               "where clinic = (?)"
                               "AND doctor = (?)"
                               "AND date = (?)", (clinic, doctor, date))
        return res.fetchone() is not None

    def add_appointment_history(self, clinic, doctor, date):
        self.cur.execute("INSERT INTO appointment VALUES (?, ?, ?)",
                         (clinic, doctor, date))
        self.conn.commit()

    def save_watch(self, region, speciality, clinic, doctor, date):
        self.cur.execute("INSERT INTO watch VALUES (null, ?, ?, ?, ?, ?)",
                         (region, speciality, clinic, doctor, date))
        self.conn.commit()

    def remove_watch(self, watch_id):
        self.cur.execute("DELETE from watch where id = (?)", (watch_id,))
        self.conn.commit()

    def get_watches(self):
        watches = self.cur.execute("SELECT * from watch")
        return watches.fetchall()

class AppointmentFinder:
    def __init__(self, authenticator):
        self.authenticator = authenticator
        self.authenticator.login()
        self.session = authenticator.session
        self.headers = authenticator.headers
        self.db = DB()

    def re_auth(self):
        self.authenticator.login()
        self.session = self.authenticator.session
        self.headers = self.authenticator.headers

    def http_get(self, url, params):
        response = self.authenticator.session.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            console.print(
                f"{datetime.datetime.now() } | Response 401. Re-authenticating"
            )
            self.re_auth()
            return self.http_get(url, params)
        else:
            console.print(
                f"[bold red]Error {response.status_code}[/bold red]: {response.text}"
            )
            return {}

    def find_appointments(self, region, specialty, clinic, start_date, doctor=None):
        appointment_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/slots"
        params = {
            "RegionIds": region,
            "SpecialtyIds": specialty,
            "ClinicIds": clinic,
            "Page": 1,
            "PageSize": 5000,
            "StartTime": start_date.isoformat(),
            "SlotSearchType": 0,
            "VisitType": "Center",
        }

        if doctor:
            params["DoctorIds"] = doctor

        response = self.http_get(appointment_url, params)

        return response.get("items", [])

    def get_watches(self):
        res = self.db.get_watches()
        if res is None:
            print("No watches found")
        return res
    def remove_watch(self, watch_id):
        self.db.remove_watch(watch_id)

    def save_watch(self, region, specialty, clinic, doctor, date):
        self.db.save_watch(region, specialty, clinic, doctor, date)

    def save_appointments_and_filter_old(self, appointments):
        new_appointments = []
        for appointment in appointments:
            clinic = appointment.get("clinic", {}).get("id", "N/A")
            doctor = appointment.get("doctor", {}).get("id", "N/A")
            date = appointment.get("appointmentDate", "N/A")

            ## check if appointment exists
            if not self.db.appointment_exists(clinic, doctor, date):
                ## Doesnt exists - Save and append
                new_appointments.append(appointment)

                self.db.add_appointment_history(clinic, doctor, date)

        return new_appointments

    def find_filters(self, region=None, specialty=None):
        filters_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/filters"

        params = {"SlotSearchType": 0}
        if region:
            params["RegionIds"] = region
        if specialty:
            params["SpecialtyIds"] = specialty

        response = self.http_get(filters_url, params)
        return response


class Notifier:
    @staticmethod
    def format_appointments(appointments):

        """Format appointments into a human-readable string."""
        if not appointments:
            return "No appointments found."

        messages = []
        for appointment in appointments:
            date = appointment.get("appointmentDate", "N/A")
            clinic = appointment.get("clinic", {}).get("name", "N/A")
            doctor = appointment.get("doctor", {}).get("name", "N/A")
            specialty = appointment.get("specialty", {}).get("name", "N/A")
            message = (
                f"Date: {date}\n"
                f"Clinic: {clinic}\n"
                f"Doctor: {doctor}\n"
                f"Specialty: {specialty}\n" + "-" * 50
            )
            messages.append(message)
        return "\n".join(messages)

    @staticmethod
    def send_notification(appointments, notifier, title):
        """Send a notification with formatted appointments."""
        message = Notifier.format_appointments(appointments)
        if notifier == "telegram":
            telegram_notify(message, title)


def display_appointments(appointments):

    if not appointments:
        console.print("No appointments found.")
    else:
        for appointment in appointments:
            date = appointment.get("appointmentDate", "N/A")
            clinic = appointment.get("clinic", {}).get("name", "N/A")
            doctor = appointment.get("doctor", {}).get("name", "N/A")
            specialty = appointment.get("specialty", {}).get("name", "N/A")
            console.print(f"Date: {date}")
            console.print(f"  Clinic: {clinic}")
            console.print(f"  Doctor: {doctor}")
            console.print(f"  Specialty: {specialty}")
            console.print("-" * 50)


def main():
    parser = argparse.ArgumentParser(description="Find appointment slots.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    find_appointment = subparsers.add_parser("find-appointment", help="Find appointment")
    find_appointment.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    find_appointment.add_argument("-s", "--specialty", required=True, type=int, action="extend", nargs="+", help="Specialty ID",)
    find_appointment.add_argument("-c", "--clinic", required=False, type=int, help="Clinic ID")
    find_appointment.add_argument("-d", "--doctor", required=False, type=int, help="Doctor ID")
    find_appointment.add_argument("-f", "--date", type=datetime.date.fromisoformat, default=datetime.date.today(), help="Start date in YYYY-MM-DD format")
    find_appointment.add_argument("-n", "--notification", required=False, help="Notification method")
    find_appointment.add_argument("-t", "--title", required=False, help="Notification title")

    add_watch = subparsers.add_parser("add-watch", help="Add watch")
    add_watch.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    add_watch.add_argument("-s", "--specialty", required=True, type=int, help="Specialty ID",)
    add_watch.add_argument("-c", "--clinic", required=False, type=int, help="Clinic ID")
    add_watch.add_argument("-d", "--doctor", required=False, type=int, help="Doctor ID")
    add_watch.add_argument("-f", "--date", type=datetime.date.fromisoformat, default=datetime.date.today(), help="Start date in YYYY-MM-DD format")

    remove_watch = subparsers.add_parser("remove-watch", help="Remove watch")
    remove_watch.add_argument("-i", "--id", required=True, type=int, help="Watch Id")

    start = subparsers.add_parser("start", help="start watch")

    list_watches = subparsers.add_parser("list-watches", help="List watches")
    list_filters = subparsers.add_parser("list-filters", help="List filters")

    list_filters_subparsers = list_filters.add_subparsers(dest="filter_type", required=True, help="Type of filter to list")

    regions = list_filters_subparsers.add_parser("regions", help="List available regions")
    specialties = list_filters_subparsers.add_parser("specialties", help="List available specialties")
    doctors = list_filters_subparsers.add_parser("doctors", help="List available doctors")
    doctors.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    doctors.add_argument("-s", "--specialty", required=True, type=int, help="Specialty ID")

    args = parser.parse_args()

    refresh_time_s = os.environ.get("REFRESH_TIME_S", 60)
    refresh_time_s = int(refresh_time_s)

    username = os.environ.get("MEDICOVER_USER")
    password = os.environ.get("MEDICOVER_PASS")

    # Authenticate
    auth = Authenticator(username, password)

    finder = AppointmentFinder(auth)

    if args.command == "find-appointment":

        # Find appointments
        appointments = finder.find_appointments(args.region, args.specialty, args.clinic, args.date, args.doctor)

        ## Filter already seen
        appointments = finder.save_appointments_and_filter_old(appointments)

        # Display appointments
        display_appointments(appointments)

        # Send notification if appointments are found
        if appointments:
            Notifier.send_notification(appointments, args.notification, args.title)

    elif args.command == "list-filters":

        if args.filter_type == "doctors":
            filters = finder.find_filters(args.region, args.specialty)
        else:
            filters = finder.find_filters()

        for r in filters[args.filter_type]:
            print(f"{r['id']} - {r['value']}")
    elif args.command == "add-watch":
        finder.save_watch(args.region, args.specialty, args.clinic, args.doctor, args.date)

    elif args.command == "remove-watch":
        finder.remove_watch(args.id)

    elif args.command == "list-watches":
        watches = finder.get_watches()
        filters = finder.find_filters()
        regions = filters.get("regions", {})
        specialties = filters.get("specialties", {})

        for watch in watches:
            region = [r.get("value") for r in regions if r.get("id") == str(watch[1])]
            specialty = [r.get("value") for r in specialties if r.get("id") == str(watch[2])]
            print(f"Id: {watch[0]}",region[0], f"({watch[1]})", specialty[0], f"({watch[2]})", watch[5])

    elif args.command == "start":
        while True:

            watches = finder.get_watches()
            for watch in watches:
                print(f"{datetime.datetime.now() } | Running watch: {watch}")
                region = watch[1]
                specialty = watch[2]
                clinic = watch[3]
                doctor = watch[4]
                date = datetime.datetime.fromisoformat(watch[5])

                # Find appointments
                appointments = finder.find_appointments(region, specialty, clinic, date, doctor)

                ## Filter already seen
                appointments = finder.save_appointments_and_filter_old(appointments)

                # Display appointments
                display_appointments(appointments)

                # Send notification if appointments are found
                if appointments:
                    speciality = appointments[0].get("specialty", {}).get("name", "N/A")

                    Notifier.send_notification(appointments, "telegram", speciality)
            sleep(refresh_time_s)

if __name__ == "__main__":
    main()
