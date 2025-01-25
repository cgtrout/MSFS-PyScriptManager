while True:
    user_input = input("Type something (or type 'exit' to quit): ")
    if user_input.lower() == "exit":
        print("Goodbye!")
        break
    print(f"You said: {user_input}")