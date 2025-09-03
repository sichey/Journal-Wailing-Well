from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import pytz  # Import the pytz library
import uuid  # Import uuid to generate unique filenames

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # For flash messages

# Directory to store uploaded voice files
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Define the time zone for the Philippines
PHILIPPINE_TIMEZONE = pytz.timezone('Asia/Manila')

# Function to connect to the database
def get_db_connection():
    conn = sqlite3.connect('wailingwell.db')
    conn.row_factory = sqlite3.Row  # To access columns by name
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?",
                       (username, username, password))
        user = cursor.fetchone()

        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Username or email already taken', 'error')
            return redirect(url_for('register'))

        cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                       (username, email, password))
        conn.commit()
        conn.close()

        flash('Registration successful, please log in', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/home')
def home():
    if 'user_id' not in session:
        flash('You need to login first', 'error')
        return redirect(url_for('login'))

    coin_toss_success = session.get('coin_toss_success', False)

    return render_template('home.html', username=session['username'], coin_toss_success=coin_toss_success)

@app.route('/toss_coin', methods=['POST'])
def toss_coin():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'You need to login first'})

    session['coin_toss_success'] = True
    return jsonify({'success': True, 'message': 'You tossed the coin successfully!'})

@app.route('/journal', methods=['GET', 'POST'])
def journal():
    if 'user_id' not in session:
        flash('You need to login first', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        entry_type = request.form['entry_type']
        user_id = session['user_id']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get the current time in Philippine Time
        created_at = datetime.now(PHILIPPINE_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')

        if entry_type == 'text':
            text_entry = request.form['text_entry']
            cursor.execute("INSERT INTO journal_entries (user_id, entry_type, content, created_at) VALUES (?, ?, ?, ?)",
                           (user_id, 'text', text_entry, created_at))

        elif entry_type == 'voice':
            # Generate a unique filename using uuid
            unique_filename = f"{user_id}_{uuid.uuid4().hex}.wav"

            # Check if the user uploaded a file
            voice_file = request.files.get('voice_entry')
            if voice_file and voice_file.filename != '':
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                voice_file.save(filepath)
                cursor.execute("INSERT INTO journal_entries (user_id, entry_type, content, created_at) VALUES (?, ?, ?, ?)",
                               (user_id, 'voice', unique_filename, created_at))

            # Otherwise, check if there's a base64 recording
            elif request.form.get('voice_recording'):
                voice_data = request.form['voice_recording']

                # Decode the base64 data and save it as a file
                import base64
                audio_data = base64.b64decode(voice_data.split(',')[1])  # Remove data URL prefix
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                with open(filepath, 'wb') as f:
                    f.write(audio_data)

                cursor.execute("INSERT INTO journal_entries (user_id, entry_type, content, created_at) VALUES (?, ?, ?, ?)",
                               (user_id, 'voice', unique_filename, created_at))

        conn.commit()
        conn.close()

        flash('Journal entry saved successfully', 'success')
        return redirect(url_for('journal'))

    return render_template('journal.html')


@app.route('/journal/book')
def journal_book():
    if 'user_id' not in session:
        flash('You need to login first', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journal_entries WHERE user_id = ?", (user_id,))
    entries = cursor.fetchall()
    conn.close()

    # Format the date and time
    formatted_entries = []
    for entry in entries:
        formatted_entry = dict(entry)
        formatted_entry['created_at'] = datetime.strptime(entry['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y (%I:%M %p)')
        formatted_entries.append(formatted_entry)

    return render_template('journal_book.html', entries=formatted_entries)


@app.route('/journal/delete/<int:entry_id>', methods=['POST'])
def delete_journal_entry(entry_id):
    if 'user_id' not in session:
        flash('You need to login first', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure the entry belongs to the user
    cursor.execute("SELECT * FROM journal_entries WHERE id = ? AND user_id = ?", (entry_id, user_id))
    entry = cursor.fetchone()

    if entry:
        # If the entry is a voice recording, delete the associated file
        if entry['entry_type'] == 'voice':
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], entry['content']))
            except OSError:
                pass  # If the file doesn't exist, continue

        cursor.execute("DELETE FROM journal_entries WHERE id = ? AND user_id = ?", (entry_id, user_id))
        conn.commit()

        flash('Journal entry deleted successfully', 'success')
    else:
        flash('Entry not found or you do not have permission to delete this entry', 'error')

    conn.close()

    return redirect(url_for('journal_book'))


if __name__ == "__main__":
    app.run(debug=True)
