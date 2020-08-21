# woocommerce_report

I created a report software with woocommerce system.

Requirements;
```
$ pip install flask
$ pip instal pandas
$ pip install pdfkit

$ brew install wkhtmltopdf
```

Before running the code, you should fill fields in configuration.json;

```
info -> name
info -> fullname
email -> sender
email -> sender password
reports -> name etc. fields..
```

Inside the reports-> woocommerce ;
There are two fields for each website
"consumer_key"
"consumer_secret"

Open your woocommerce website panel, **woocommerce-> settings -> advanced -> RESTAPI**

Create a rest api key, it will provide these two fields. So you can access woocommerce reports directly.

Inside these program, I only provided **status==completed**
transaction reports and their tax calculation for sweden.
You can play with code to change them.

If you want to work directly from code use main method, otherwise I created a web gui with flask.



https://www.patreon.com/ozkulah
 