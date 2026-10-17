
import os
import uuid
from decimal import Decimal
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)

# Replace this with your PostgreSQL username/password.
# If your password has special URL characters, URL-encode them.
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-to-a-long-random-secret"
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:root@localhost:5432/premium_bottles"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


# ---------------- DATABASE MODELS ----------------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    contact = db.Column(db.String(20), unique=True, nullable=False)
    profile_picture = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=50)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Confirmed")
    items = db.relationship(
        "OrderItem", backref="order", cascade="all, delete-orphan"
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)


# ---------------- HELPERS ----------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    return db.session.get(User, session["user_id"])


def save_picture(file):
    if not file or not file.filename:
        return None

    try:
        image = Image.open(file.stream)
        image.verify()
        file.stream.seek(0)
        image = Image.open(file.stream)
        image.load()

        if image.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Use JPG, PNG or WEBP.")

        image.thumbnail((600, 600))
        filename = uuid.uuid4().hex + ".jpg"
        path = os.path.join(UPLOAD_FOLDER, filename)
        image.convert("RGB").save(path, "JPEG", quality=88)
        return filename

    except Exception:
        raise ValueError("Please upload a valid JPG, PNG or WEBP image.")


def seed_products():
    if Product.query.count() == 0:
        products = [
            Product(
                name="AURORA Matte Black",
                description="Double-wall insulated stainless steel bottle.",
                price=Decimal("899.00"),
                image_url="https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=700",
                stock=30
            ),
            Product(
                name="VERDE Emerald",
                description="Elegant reusable bottle for everyday luxury.",
                price=Decimal("1099.00"),
                image_url="https://images.unsplash.com/photo-1608270586620-248524c67de9?w=700",
                stock=25
            ),
            Product(
                name="PURE Silver",
                description="Minimal silver steel bottle for work and travel.",
                price=Decimal("699.00"),
                image_url="https://images.unsplash.com/photo-1523362628745-0c100150b504?w=700",
                stock=40
            ),
            Product(
                name="NOVA Travel",
                description="A stylish companion for your daily adventures.",
                price=Decimal("1299.00"),
                image_url="https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=700",
                stock=20
            )
        ]
        db.session.add_all(products)
        db.session.commit()


# ---------------- REGISTRATION ----------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("register"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        contact = request.form.get("contact", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, address, contact, password, confirm]):
            flash("Please fill in all required fields.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if User.query.filter_by(contact=contact).first():
            flash("This contact number is already registered.", "error")
            return render_template("register.html")

        try:
            picture = save_picture(request.files.get("profile_picture"))
            user = User(
                name=name,
                address=address,
                contact=contact,
                profile_picture=picture,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except Exception:
            db.session.rollback()
            flash("Registration failed. Please check your details.", "error")

    return render_template("register.html")


# ---------------- LOGIN / LOGOUT ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        contact = request.form.get("contact", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(contact=contact).first()

        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["cart"] = {}
            flash("Hurray! You're in. Welcome to the premium experience!", "success")
            return redirect(url_for("home"))

        flash("Incorrect contact number or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------- SHOP ----------------

@app.route("/home")
@login_required
def home():
    products = Product.query.order_by(Product.id).all()
    return render_template("home.html", products=products, user=current_user())


@app.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = db.session.get(Product, product_id)
    if not product or product.stock < 1:
        flash("This product is currently unavailable.", "error")
        return redirect(url_for("home"))

    cart = session.get("cart", {})
    key = str(product_id)
    quantity = int(cart.get(key, 0))

    if quantity >= product.stock:
        flash("Maximum available stock already added.", "error")
    else:
        cart[key] = quantity + 1
        session["cart"] = cart
        session.modified = True
        flash(f"{product.name} added to your cart.", "success")

    return redirect(url_for("home"))


# ---------------- CART / ORDER ----------------

@app.route("/cart")
@login_required
def cart():
    cart_data = session.get("cart", {})
    items = []
    total = Decimal("0.00")

    for product_id, quantity in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product and quantity > 0:
            quantity = min(int(quantity), product.stock)
            subtotal = product.price * quantity
            total += subtotal
            items.append({
                "product": product,
                "quantity": quantity,
                "subtotal": subtotal
            })

    return render_template("cart.html", items=items, total=total)


@app.route("/cart/remove/<int:product_id>", methods=["POST"])
@login_required
def remove_from_cart(product_id):
    cart_data = session.get("cart", {})
    cart_data.pop(str(product_id), None)
    session["cart"] = cart_data
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart_data = session.get("cart", {})
    if not cart_data:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))

    order = Order(user_id=session["user_id"], total=Decimal("0.00"))
    total = Decimal("0.00")

    try:
        db.session.add(order)
        db.session.flush()

        for product_id, quantity in cart_data.items():
            product = db.session.get(Product, int(product_id))
            quantity = int(quantity)

            if not product or quantity < 1 or product.stock < quantity:
                raise ValueError("Stock changed. Please review your cart.")

            subtotal = product.price * quantity
            total += subtotal

            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price
            ))
            product.stock -= quantity

        order.total = total
        db.session.commit()
        session["cart"] = {}

        return redirect(url_for("success", order_id=order.id))

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
        return redirect(url_for("cart"))
    except Exception:
        db.session.rollback()
        flash("Unable to place your order. Please try again.", "error")
        return redirect(url_for("cart"))


@app.route("/success/<int:order_id>")
@login_required
def success(order_id):
    order = db.session.get(Order, order_id)
    if not order or order.user_id != session["user_id"]:
        abort(404)
    return render_template("success.html", order=order)


# ---------------- PROFILE / EDIT ----------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        contact = request.form.get("contact", "").strip()

        if not all([name, address, contact]):
            flash("Name, address and contact are required.", "error")
            return render_template("profile.html", user=user)

        existing = User.query.filter_by(contact=contact).first()
        if existing and existing.id != user.id:
            flash("This contact number belongs to another account.", "error")
            return render_template("profile.html", user=user)

        try:
            picture = save_picture(request.files.get("profile_picture"))
            user.name = name
            user.address = address
            user.contact = contact

            if picture:
                old_picture = user.profile_picture
                user.profile_picture = picture
                if old_picture:
                    old_path = os.path.join(UPLOAD_FOLDER, old_picture)
                    if os.path.isfile(old_path):
                        os.remove(old_path)

            db.session.commit()
            flash("Your profile has been updated.", "success")
            return redirect(url_for("profile"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except Exception:
            db.session.rollback()
            flash("Unable to update profile.", "error")

    return render_template("profile.html", user=user)


# ---------------- START ----------------

with app.app_context():
    db.create_all()
    seed_products()


if __name__ == "__main__":
    app.run(debug=True)
