#!/usr/local/bin/python 3.6
# -*- coding: UTF-8 -*-
from datetime import date, timedelta
import json
import pandas as pd
import flask
import pdfkit
import smtplib, ssl
import sys, os

from flask import render_template, request, redirect, url_for, Flask
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from woocommerce import API

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask('my app', template_folder=template_folder)
    bundle_dir = sys._MEIPASS
else:
    # running live
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask('my app')
CONFIG_PATH = os.path.join(bundle_dir, 'configuration.json')


class Report:
    detail_table = pd.DataFrame()
    output_html = ""
    mat_order_totalt = int
    avgift_sum = int
    gross_sum = int

    def __init__(self, config, customer_data):
        self.config = config
        self.report = customer_data
        self.customer_name = customer_data["name"]
        self.wcapi = API(
            url=self.report["woocommerce"]["url"],  # Your store URL
            consumer_key=self.report["woocommerce"]["consumer_key"],  # Your consumer key
            consumer_secret=self.report["woocommerce"]["consumer_secret"],  # Your consumer secret
            wp_api=self.report["woocommerce"]["wp_api"],  # Enable the WP REST API integration
            version=self.report["woocommerce"]["version"]  # WooCommerce WP REST API version
        )

    def read_from_woocommerce(self, start_date, end_date):
        order_getter = self.wcapi.get("orders", params={"status": "completed", "after": start_date, "before": end_date})

        total_pages = int(order_getter.headers['X-WP-TotalPages'])
        orders = []
        for i in range(1, total_pages + 1):
            order = self.wcapi.get("orders?&page=" + str(i),
                                   params={"status": "completed", "after": start_date, "before": end_date}).json()
            orders += order
        new_order_list = []

        for order in orders:
            new_order = {
                "order_id": order["id"],
                "data_created": order["date_created"],
                "payment_method": order["payment_method"],
                "net_total": float(order["total"]) - float(order["shipping_total"]),
                "shipping_total": float(order["shipping_total"]),
                "total_sales": float(order["total"])
            }
            new_order_list.append(new_order)

        self.detail_table = pd.DataFrame(new_order_list,
                                         columns=["order_id", "data_created", "payment_method", "net_total",
                                                  "shipping_total", "total_sales"])
        self.detail_table.loc[self.detail_table["payment_method"] == "kco", "payment_method"] = "Klarna"
        self.detail_table["payment_method"] = self.detail_table["payment_method"].str.capitalize()

    def read_from_csv(self, file_name):
        self.detail_table = pd.read_csv(file_name, delimiter=',')

    def get_moms_report(self):
        self.mat_order_totalt = self.detail_table["net_total"].sum()
        self.avgift_sum = self.detail_table["shipping_total"].sum()
        self.gross_sum = self.detail_table["total_sales"].sum()
        mat_order_net = round(self.mat_order_totalt / 1.12, 2)
        mat_order_mom = round(self.mat_order_totalt - mat_order_net, 2)
        avgift_net = round(self.avgift_sum / 1.25, 2)
        avgift_mom = round(self.avgift_sum - avgift_net, 2)
        moms_total = mat_order_mom + avgift_mom
        netto_total = mat_order_net + avgift_net

        moms_report = list()
        moms_report.append(["Moms 12%", mat_order_net, mat_order_mom, self.mat_order_totalt])
        moms_report.append(["Moms 25%", avgift_net, avgift_mom, self.avgift_sum])
        moms_report.append(["Totalsumma", netto_total, moms_total, self.gross_sum])
        return moms_report

    def get_payment_report(self):
        payment_method = self.detail_table.groupby(["payment_method"], as_index=False).agg({'total_sales': ["sum"]})
        payment_method.columns = ["Betalningsmetod", "Sum"]
        payment_method.reset_index()
        payment_sum = payment_method["Sum"].sum()
        payment_method.loc[len(payment_method)] = ["Totalsumma", payment_sum]
        return payment_method.values.tolist()

    def get_date_range(self, sp="."):
        d = date.today()
        d2 = date.today()
        d2 = d2.replace(day=1)
        d = d.replace(month=d.month)
        d = d.replace(day=1)
        start_date = d2.replace(month=d2.month - 1)  # TODO this will be only 1 month
        end_date = d - timedelta(days=1)
        if sp == "-":
            return start_date.strftime("%Y-%m-%d 00:00:00"), end_date.strftime("%Y-%m-%d 23:59:59")
        elif sp == "/":
            return start_date.strftime("%Y-%m-%dT00:00:00"), end_date.strftime("%Y-%m-%dT23:59:59")
        else:
            return start_date.strftime("%d.%m.%Y"), end_date.strftime("%d.%m.%Y")

    def create_html(self, start_date, end_date):
        moms_report = self.get_moms_report()
        payments_report = self.get_payment_report()

        month_report = start_date.split("-")
        month_report = "_".join(month_report[:2])
        detail_report = self.detail_table
        detail_report.loc[len(detail_report)] = ["", "", "", self.mat_order_totalt, self.avgift_sum, self.gross_sum]
        org_nummer = self.report["org_nummer"]
        website = self.report["website"]
        full_report = {
            "provider_fullname": self.config["info"]["fullname"],
            "provider_address": self.config["info"]["address"],
            "company_name": self.customer_name,
            "org_nummer": org_nummer,
            "website": website,
            "detail_report": detail_report.values.tolist(),
            "moms_report": moms_report,
            "payments_report": payments_report,
            "start_date": start_date,
            "end_date": end_date
        }
        customer = self.customer_name.replace(" ", "_")
        self.output_html =   customer + "_report_" + month_report + ".html"
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS + "/output/"
        else:
            bundle_dir = "output/"
        self.output_html = bundle_dir + self.output_html

        if not os.path.exists(bundle_dir):
            os.mkdir(bundle_dir)

        with app.app_context():
            print(self.output_html)
            f = open(self.output_html, "w")
            rendered = render_template('report.html', title="Provider Report", result=full_report)
            f.write(rendered)
            f.close()

    def create_pdf(self):
        pdfkit.from_file(self.output_html, self.output_html.replace(".html", ".pdf"))
        self.output_pdf = self.output_html.replace(".html", ".pdf")

    def send_mail(self, start_date, end_date):
        subject = (self.config["email"]["subject"]).format(start_date, end_date)
        body = (self.config["email"]["body"]).format(self.customer_name)
        sender_email = self.config["email"]["sender"]
        receiver_email = self.report["email"]
        password = self.config["email"]["sender_pass"]

        # Create a multipart message and set headers
        message = MIMEMultipart()
        # message["From"] = sender_email
        # message["To"] = receiver_email
        message["Subject"] = subject
        # message["Bcc"] = receiver_email  # TODO info to boss

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        filepath = self.output_pdf  # In same directory as script
        filename = self.output_pdf.split("/")[-1]

        # Open PDF file in binary mode
        with open(filepath, "rb") as attachment:
            # Add file as application/octet-stream
            # Email client can usually download this automatically as attachment
            part = MIMEBase("application", "pdf")
            part.set_payload(attachment.read())

        # Encode file in ASCII characters to send by email
        encoders.encode_base64(part)

        # Add header as key/value pair to attachment part
        part.add_header(
            "Content-Disposition",
            f"attachment; filename= {filename}",
        )

        # Add attachment to message and convert message to string
        message.attach(part)
        text = message.as_string()
        try:
            # Log in to server using secure context and send email
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("mailcluster.loopia.se", 465, context=context) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, receiver_email, text)
        except Exception as e:
            print(e)


def error_mail(sender_email, password, receiver_email, subject, body):
    # Create a multipart message and set headers
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message["Bcc"] = receiver_email  # TODO info to boss

    # Add body to email
    message.attach(MIMEText(body, "plain"))
    text = message.as_string()

    # Log in to server using secure context and send email
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("mailcluster.loopia.se", 465, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, text)


def update_config(new_config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(new_config, f, indent=4)


def load_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config


def get_config_for_table():
    config = load_config()
    customer_count = len(config["reports"])
    data_details = []
    for customer in config["reports"]:
        data_details.append({
            "name": customer["name"],
            "org_num": customer["org_nummer"],
            "email": ",".join(customer["email"])
        })
    return data_details


def get_customer(org_nummer):
    print("get customer")
    config = load_config()
    customers = config["reports"]
    for customer in customers:
        if customer["org_nummer"] == org_nummer:
            return customer
    return None


def add_update_customer(id, name, org_num, website, email, con_key, con_secret):
    config = load_config()
    emails = email.split(",")
    website_woo = website
    if "https://" not in website_woo:
        website_woo = "https://" + website_woo
    cust = {
        "name": name,
        "org_nummer": org_num,
        "website": website,
        "email": emails,
        "adress": "",
        "woocommerce": {
            "url": website_woo,
            "consumer_key": con_key,
            "consumer_secret": con_secret,
            "wp_api": True,
            "version": "wc/v3"
        }
    }

    customer = get_customer(id)

    if not customer:
        config["reports"].append(cust)
    else:
        config["reports"] = [value for value in config["reports"] if value["org_nummer"] != id]
        config["reports"].append(cust)

    # pprint.pprint(config)
    update_config(config)


def delete_customer(org_num):
    config = load_config()
    config["reports"] = [value for value in config["reports"] if value["org_nummer"] != org_num]
    update_config(config)


def initialize():
    data_details = get_config_for_table()
    data = {"detail_report": data_details}
    data["active_customer"] = {
        "org_nummer": "",
        "name": "",
        "website": "",
        "email": "",
        "con_key": "",
        "con_secret": ""
    }
    return data


def main():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    customer_count = len(config["reports"])
    print("Customer Count: {}".format(customer_count))
    sender_email, password, receiver_email = config["email"]["sender"], config["email"]["sender_pass"], config["email"][
        "sender"]
    for i in range(0, customer_count):
        customer = config["reports"][i]["name"]
        report = Report(config, i)
        try:
            print("Reporting... {}".format(config["reports"][i]["name"]))
            print("Read from Woo commerce")
            report.read_from_woocommerce()
            print("Create Report Html...")
            report.create_html()
            print("Create Report pdf...")
            report.create_pdf()
            print("Send Mail...")
            # report.send_mail()
            print("Report sended for {}".format(config["reports"][i]["name"]))
        except Exception as e:
            subject = "Report Error for {}".format(customer)
            error = "Error taken {} \n for customer {}".format(e, customer)
            print(subject)
            error_mail(sender_email, password, config["email"]["sender"], subject, error)


@app.route("/add-config", methods=["GET"])
def add_config():
    print("add Config")
    id = request.args.get("id")
    name = request.args.get("name")
    org_num = request.args.get("org_nummer")
    website = request.args.get("website")
    email = request.args.get("email")
    con_key = request.args.get("con_key")
    con_secret = request.args.get("con_secret")
    add_update_customer(id, name, org_num, website, email, con_key, con_secret)
    return redirect(url_for('index'))


@app.route("/update", methods=["GET"])
def update_company():
    org_nummer = request.args.get("org_num")
    if not org_nummer:
        return
    customer = get_customer(org_nummer)
    data_details = get_config_for_table()
    data = {"detail_report": data_details}
    data["active_customer"] = {
        "org_nummer": customer["org_nummer"],
        "name": customer["name"],
        "website": customer["website"],
        "email": ",".join(customer["email"]),
        "con_key": customer["woocommerce"]["consumer_key"],
        "con_secret": customer["woocommerce"]["consumer_secret"]
    }
    return render_template('main.html', title="Provider Report", result=data)


@app.route("/delete", methods=["GET"])
def delete_company():
    org_nummer = request.args.get("org_num")
    delete_customer(org_nummer)
    return redirect(url_for('index'))


@app.route("/send_mail")
def send_mail():
    print("send mail")
    org_nummers = request.args.get("ids")
    org_nummers = org_nummers.split(",")
    config = load_config()
    date_start_woo = request.args.get("date_start") + "T00:00:00"
    date_start = request.args.get("date_start")
    date_end_woo = request.args.get("date_end") + "T00:00:00"
    date_end = request.args.get("date_end")

    sender_email, password, receiver_email = config["email"]["sender"], config["email"]["sender_pass"], config["email"][
        "sender"]
    for org_num in org_nummers:
        customer_data = [value for value in config["reports"] if value["org_nummer"] == org_num][0]
        customer = customer_data["name"]
        report = Report(config, customer_data)
        try:
            print("Reporting... {}".format(customer))
            print("Read from Woo commerce")
            report.read_from_woocommerce(date_start_woo, date_end_woo)
            print("Create Report Html...")
            report.create_html(date_start, date_end)
            print("Create Report pdf...")
            report.create_pdf()
            print("Send Mail...")
            report.send_mail(date_start, date_end)
            print("Report sended for {}".format(customer))
        except Exception as e:
            subject = "Report Error for {}".format(customer)
            error = "Error taken {} \n for customer {}".format(e, customer)
            print(subject)
            error_mail(sender_email, password, config["email"]["sender"], subject, error)

    return redirect(url_for('index'))


@app.route("/")
def index():
    return render_template('main.html', title="Provider Report", result=initialize())


if __name__ == '__main__':
    app.run()
