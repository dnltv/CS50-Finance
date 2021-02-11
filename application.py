import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query to DB
    rows = db.execute('SELECT * FROM stocks WHERE user_id = :user',
        user=session['user_id'])

    cash = db.execute('SELECT cash FROM users WHERE id = :user',
        user=session['user_id'])[0]['cash']

    total = cash
    stocks = []

    for index, row in enumerate(rows):
        stock_info = lookup(row['symbol'])

        stocks.append(list((stock_info['symbol'], stock_info['name'], row['shares'], stock_info['price'],
            round(stock_info['price'] * row['shares'], 2))))
        total += stocks[index][4]

    return render_template('index.html', stocks=stocks, cash=round(cash, 2), total=round(total, 2))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == 'POST':
        shares = int(request.form.get('shares'))
        symbol = lookup(request.form.get('symbol'))['symbol']

        if not lookup(symbol):
            return apology('Could not find a stock')

        if shares <= 0:
            return apology('Could be a positivfle number of shares')

        # Calculate value after transaction
        price = lookup(symbol)['price']
        cash = db.execute('SELECT cash FROM users WHERE id = :user',
            user=session['user_id'])[0]['cash']
        cash1 = cash - price * float(shares)

        # Check cash
        if cash1 < 0:
            return apology('You do not have enough money for this transaction')

        stock = db.execute('SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol',
            user=session['user_id'], symbol=symbol)

        # Insert new row into stock table
        if not stock:
            db.execute('INSERT INTO stocks(user_id, symbol, shares) VALUES (:user, :symbol, :shares)',
                user=session['user_id'], symbol=symbol, shares=shares)
        # Update into stock table
        else:
            shares += stock[0]['shares']

            db.execute('UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol',
                user=session['user_id'], symbol=symbol, shares=shares)

        # Update users cash
        db.execute('UPDATE users SET cash = :cash WHERE id = :user',
            cash=cash1, user=session['user_id'])

        # Update history table
        db.execute('INSERT INTO transactions(user_id, symbol, shares, value) VALUES (:user, :symbol, :shares, :value)',
            user=session['user_id'], symbol=symbol, shares=shares, value=round(price*float(shares)))

        # RD to index page
        flash('Bought!')
        return redirect('/')

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template('/buy.html')


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query DB for history
    rows = db.execute('SELECT * FROM transactions WHERE user_id = :user',
        user=session['user_id'])

    trans = []
    for row in rows:
        stock_info = lookup(row['symbol'])

        trans.append(list((stock_info['symbol'], stock_info['name'], row['shares'], row['value'], row['date'])))

    # RD to index page
    return render_template('history.html', trans=trans)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == 'POST':

        stock = lookup(request.form.get('symbol'))

        if not stock:
            return apology('Could not find the stock')
        return render_template('quote.html', stock=stock)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template('quote.html', stock='')


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirm-password is correct
        elif request.form.get("password") != request.form.get("confirm-password"):
            return apology("The passwords don't match", 403)

        # Query DB for username if already exists
        elif db.execute("SELECT * FROM users WHERE username = :username",
            username=request.form.get("username")):
            return apology("Username already taken", 403)

        # Insert user and hash of the pass into the table
        db.execute("INSERT INTO users(username, hash) VALUES (:username, :hash)",
            username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Query DB for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
            username=request.form.get("username"))

        # Remember the user
        session["user_id"] = rows[0]["id"]

        # RD user to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached routed via POST (as by submitting a form via POST)
    if request.method == 'POST':

        shares = int(request.form.get('shares'))
        symbol = request.form.get('symbol')
        price = lookup(symbol)['price']
        value = round(price*float(shares))

        shares_b = db.execute('SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol',
            user=session['user_id'], symbol=symbol)[0]['shares']
        shares_a = shares_b - shares

        # Delete stock from table, if user sold all of shares
        if shares_a == 0:
            db.execute('DELETE FROM stocks WHERE user_id = :user AND symbol = :symbol',
                user=session['user_id'], symbol=symbol)

        # Check
        elif shares_a < 0:
            return apology('Thats more than you have')

        # Else update with new line
        else:
            db.execute('UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol',
                user=session['user_id'], shares=shares_a, symbol=symbol)

        # Calculate and update users cash
        cash = db.execute('SELECT cash FROM users WHERE id = :user',
            user=session['user_id'])[0]['cash']

        cash1 = cash + price * float(shares)

        db.execute('UPDATE users SET cash = :cash WHERE id = :user',
            user=session['user_id'], cash=cash1)

        # Update history table
        db.execute('INSERT INTO transactions(user_id, symbol, shares, value) VALUES (:user, :symbol, :shares, :value)',
            user=session['user_id'], symbol=symbol, shares=-shares, value=value)

        # RD to homepage
        flash('Sold!')
        return redirect('/')

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Query DB for history
        rows=db.execute('SELECT symbol, shares FROM stocks WHERE user_id = :user',
            user=session['user_id'])

        # Dict with the availability of the stocks
        stocks = {}
        for row in rows:
            stocks[row['symbol']] = row['shares']

        return render_template('sell.html', stocks=stocks)




def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
