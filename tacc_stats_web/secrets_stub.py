DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'dmalone',                      # Or path to database file if using sqlite3.
        'USER': 'dmalone',                      # Not used with sqlite3.
        'PASSWORD': 'dmalone',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}


# Make this unique, and don't share it with anybody.
SECRET_KEY = 'jksadfajksdlghklsdhgfjklsadhglsdhghsadlkfjhl'
