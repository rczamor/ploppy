"""Simple test to verify Streamlit is working."""

import streamlit as st
import time

st.set_page_config(page_title="Test App", layout="wide")

st.title("🧪 Streamlit Test Page")
st.write("If you can see this, Streamlit is working!")

# Simple counter
if "counter" not in st.session_state:
    st.session_state.counter = 0

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Increment"):
        st.session_state.counter += 1

with col2:
    if st.button("Decrement"):
        st.session_state.counter -= 1

with col3:
    if st.button("Reset"):
        st.session_state.counter = 0

st.metric("Counter Value", st.session_state.counter)

# Test basic functionality
st.subheader("Test Elements")
st.text_input("Enter some text:")
st.slider("Select a value:", 0, 100, 50)
st.checkbox("Check me!")

# Current time
st.write(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

if st.button("Refresh Page"):
    st.rerun()