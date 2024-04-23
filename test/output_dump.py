from pynput.keyboard import Key, Controller

def insert_at_cursor(text):
    """
    Inserts text at the current cursor location. If the text contains a backspace character,
    it deletes the character before the cursor.
    
    Args:
    - text: The text to be inserted at the cursor location.
    """
    print("The text is", text)
    keyboard = Controller()
    keyboard = Controller()
    for char in text:
        if char == "\b":  # If the character is a backspace
            keyboard.release(Key.backspace)
        elif char == "\n":  # If the character is a new line
            keyboard.release(Key.enter)
        else:
            keyboard.type(char)

import time
print("Please put your cursor in the input field.")
time.sleep(3)  # Wait for 3 seconds to allow the person to put the cursor at the typing location
for i in range(1, 5):
    text_to_insert = f"Call number {i}"
    insert_at_cursor(text_to_insert)
    time.sleep(0.01)  # Sleep for 10 milliseconds

