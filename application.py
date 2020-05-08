import os
import string
import requests
import math

from flask import Flask, session, render_template
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import *

app = Flask(__name__)

# Check for environment variables
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

if not os.getenv("GOODREADS_API_KEY"):
    raise RuntimeError("GOODREADS_API_KEY is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show homepage from which to search books"""
        
    if request.method == "POST":
        term = request.form.get("search_bar")
        term = term.strip()
        if not term:
            return render_template("index.html")
        query_type = request.form.get("radios")
        return redirect("/" + query_type + "/" + term)
    else:
        return render_template("index.html")

#route for search results
@app.route("/<string:query_type>/<string:query>")
@login_required
def search(query_type, query):
    query = query.upper()

    if query_type=="title":
        rows = db.execute("SELECT * FROM books WHERE upper(title) LIKE CONCAT('%', :r, '%')", {"r": query}).fetchall()
    elif query_type=="author":
        rows = db.execute("SELECT * FROM books WHERE upper(author) LIKE CONCAT('%', :r, '%')", {"r": query}).fetchall()
    else:
        rows = db.execute("SELECT * FROM books WHERE upper(isbn) LIKE CONCAT('%', :r, '%')", {"r": query}).fetchall()

    if len(rows)==0:
        return render_template("error.html", error="No Matches")

    return render_template("search_results.html", results=rows, length=len(rows))

#route for each book
@app.route("/book/<string:book_title>", methods=["GET", "POST"])
@login_required
def book(book_title):
    if request.method == "GET":
        row = db.execute("SELECT * FROM books WHERE title = :title", {"title": book_title}).fetchone()
        if row is None:
            return render_template("error.html", error="Book Doesn't Exist!")

        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": os.getenv("GOODREADS_API_KEY"), "isbns": row.isbn})
        data = res.json()
        rating = float(data['books'][0]['average_rating'])
        
        reviews = db.execute("SELECT username, review, time FROM reviews WHERE isbn = :isbn", {"isbn": row.isbn}).fetchall()
        review_items = len(reviews)
        
        return render_template("book.html", book_title=row.title, book_author=row.author, book_isbn=row.isbn, book_year=row.year, rating=rating, star_rating=math.floor(rating), reviews=reviews, review_items=review_items)
    
    else:
        if not request.form.get("review_new"):
            return redirect("/book/" + book_title)

        row = db.execute("SELECT * FROM books WHERE title = :title", {"title": book_title}).fetchone()
        if row is None:
            return render_template("error.html", error="Book Doesn't Exist!")
        
        user = session["user_id"]
        username = db.execute("SELECT username FROM users WHERE id=:id", {"id": user}).fetchone()

        new_review = request.form.get("review_new")

        db.execute("INSERT INTO reviews (username, isbn, review) VALUES (:username, :isbn, :review)", {"username": username.username, "isbn":row.isbn, "review": new_review})
        db.commit()
        return redirect("/book/" + book_title)
        

#route for register
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register User"""
    if request.method == "POST":

        if not request.form.get("username"):
            return render_template("error.html", error="Must Provide Username")
        if not request.form.get("password"):
            return render_template("error.html", error="Must Provide Password")
        if not request.form.get("confirm password"):
            return render_template("error.html", error="Must Provide Confirmation Password")
        if str(request.form.get("password")) != str(request.form.get("password")):
            return render_template("error.html", error="Password and Confirmation Do Not Match")
      
        rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall()
        if len(rows) != 0:
            return render_template("error.html", error="Username Already Taken")

        user = request.form.get("username")
        hash_password = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    {"username": user, "hash": hash_password})
        db.commit()
        return redirect("/")
    else:
        return render_template("register.html")

#route for login
@app.route("/login", methods=["GET", "POST"])
def login():
    """Login User"""
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return render_template("error.html", error="Must Provide Username")
        if not request.form.get("password"):
            return render_template("error.html", error="Must Provide Password")

        username = request.form.get("username")
        password = request.form.get("password")
        user = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()
        if user is None:
            return render_template("error.html", error="Invalid Username")
        if not check_password_hash(user.hash, password):
            return render_template("error.html", error="Invalid Password")

        session["user_id"] = user.id
        return redirect("/")
            
    else:
        return render_template("login.html")



#route for logout
@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/")

