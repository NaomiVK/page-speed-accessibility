import streamlit as st
import pandas as pd
import requests
import os
import time
import json # To help parse potential error messages
import altair as st_alt # For better visualizations

# --- Configuration ---
API_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
API_CALL_DELAY = 0.8 # Slightly increased delay might be needed for larger responses
REQUEST_TIMEOUT = 120 # Increased timeout as getting all audits might take longer
OPENROUTER_TIMEOUT = 30 # Timeout for OpenRouter API calls

# --- Helper Functions ---
def get_audit_category(score, display_mode):
    """
    Categorizes audits into clear groups for better understanding.
    
    Args:
        score: The audit score (0, 1, or None)
        display_mode: The display mode (binary, manual, informative, notApplicable)
        
    Returns:
        str: Category name ('failed', 'manual_check', 'passed', 'not_applicable')
    """
    if score == 0 and display_mode == 'binary':
        return "failed"
    elif display_mode in ['manual', 'informative']:
        return "manual_check"
    elif score == 1 and display_mode == 'binary':
        return "passed"
    elif display_mode == 'notApplicable':
        return "not_applicable"
    else:
        return "other"

# --- Helper Function to Call PageSpeed Insights API ---
# UPDATED: Returns detailed audit results along with the score for all categories
def get_psi_accessibility_details(url_to_check, api_key, strategy):
    """
    Fetches the PageSpeed Insights accessibility score and detailed audit results
    for a given URL using the specified strategy.

    Args:
        url_to_check (str): The URL to analyze.
        api_key (str): Your Google PageSpeed Insights API key.
        strategy (str): 'mobile' or 'desktop'.

    Returns:
        dict: A dictionary containing 'score' (str) and 'audits' (list of dicts),
              or an error structure {'error': str}.
    """
    # Basic URL validation and cleanup
    if not url_to_check or not isinstance(url_to_check, str) or not url_to_check.strip():
        return {"error": "Invalid URL provided"}
    url_to_check = url_to_check.strip()
    if not url_to_check.startswith(('http://', 'https://')):
        url_to_check = 'https://' + url_to_check

    params = {
        'url': url_to_check,
        'key': api_key,
        'category': 'ACCESSIBILITY',
        'strategy': strategy
    }

    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        result = response.json()

        lighthouse_result = result.get('lighthouseResult')
        if not lighthouse_result:
             error_message = result.get('error', {}).get('message', 'No lighthouseResult in API response.')
             st.warning(f"Could not get lighthouseResult for {url_to_check}. API Message: {error_message}")
             return {"error": f"API Error: {error_message}"}


        # --- Extract Score ---
        accessibility_category = lighthouse_result.get('categories', {}).get('accessibility', {})
        score_raw = accessibility_category.get('score')
        score_display = "N/A"
        if score_raw is not None:
            score_display = f"{int(score_raw * 100)}%"

        # --- Extract Detailed Audits ---
        all_audits_dict = lighthouse_result.get('audits', {})
        accessibility_audit_refs = accessibility_category.get('auditRefs', [])

        detailed_audits = []
        for ref in accessibility_audit_refs:
            audit_id = ref.get('id')
            audit_data = all_audits_dict.get(audit_id)
            if not audit_data:
                continue # Skip if audit data not found

            # Get all audits, not just failures
            score = audit_data.get('score')
            display_mode = audit_data.get('scoreDisplayMode')
            
            # Extract details and snippet for all audits
            details = audit_data.get('details', {})
            snippet = ""
            items = details.get('items', [])
            if items and isinstance(items, list) and len(items) > 0:
                first_item = items[0]
                if isinstance(first_item, dict):
                    snippet = first_item.get('node', {}).get('snippet') or first_item.get('snippet', '')
            
            # Categorize the audit
            category = get_audit_category(score, display_mode)
            
            # Add all audits to the list with category information
            detailed_audits.append({
                'id': audit_id,
                'title': audit_data.get('title', 'N/A'),
                'description': audit_data.get('description', 'N/A'),
                'score': score,
                'displayMode': display_mode,
                'category': category,
                'details_snippet': snippet if snippet else " (No specific item snippet)"
            })

        return {'score': score_display, 'audits': detailed_audits}

    except requests.exceptions.Timeout:
        st.warning(f"Request timed out ({REQUEST_TIMEOUT}s) for {url_to_check}")
        return {"error": "Error: Timeout"}
    except requests.exceptions.HTTPError as e:
         error_detail = f"HTTP Error {e.response.status_code}"
         try:
             error_content = response.json().get('error', {})
             error_detail = f"API Error {error_content.get('code', e.response.status_code)}: {error_content.get('message', 'No details provided')}"
         except (json.JSONDecodeError, AttributeError): # Handle non-JSON or unexpected structure
              error_detail = f"HTTP Error {e.response.status_code}: {response.text[:200]}" # Show part of the raw response
         st.warning(f"Failed for {url_to_check}: {error_detail}")
         return {"error": error_detail}
    except requests.exceptions.RequestException as e:
        st.warning(f"Network error for {url_to_check}: {e}")
        return {"error": f"Error: Network Issue ({e})"}
    except (KeyError, AttributeError) as e: # Catch issues navigating the JSON response
         st.warning(f"Unexpected API response structure for {url_to_check}. Check response format. Error: {e}")
         # Optionally log the full response here for debugging if needed
         return {"error": f"Error: Unexpected API Response Structure ({e})"}
    except Exception as e: # Catch any other unexpected errors
        st.error(f"An unexpected error occurred processing {url_to_check}: {e}")
        return {"error": f"Error: Unexpected ({e})"}

# --- Function to Call OpenRouter API for Gemini Analysis ---
def get_gemini_analysis(failed_audits, url):
    """
    Send failed accessibility audits to Gemini 2.5 Pro via OpenRouter for analysis.
    
    Args:
        failed_audits (list): List of failed accessibility audits
        url (str): The URL that was analyzed
        
    Returns:
        str: Gemini's analysis and recommendations, or error message
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "Error: OPENROUTER_API_KEY environment variable not found."
    
    # Format the prompt with all audit information
    prompt = f"""Analyze these accessibility failures for {url} and provide a concise summary.

Your response should:
1. Explain each issue in plain, non-technical language
2. Provide brief, specific recommendations on how to fix each issue
3. Be concise and to the point - avoid unnecessary explanations
4. Prioritize the most critical accessibility issues first

Here are the accessibility failures to analyze:

"""
    
    for i, audit in enumerate(failed_audits, 1):
        prompt += f"{i}. Issue: {audit.get('title')}\n"
        prompt += f"   Description: {audit.get('description')}\n"
        if audit.get('details_snippet') and audit.get('details_snippet') != " (No specific item snippet)":
            prompt += f"   Code Snippet: {audit.get('details_snippet')}\n"
        prompt += "\n"
    
    # Prepare the request to OpenRouter
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "google/gemini-2.5-pro-preview-03-25",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4096,
        "temperature": 0.3
    }
    
    try:
        response = requests.post(
            OPENROUTER_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=OPENROUTER_TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        
        # Extract the analysis from the response
        analysis = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not analysis:
            return "Error: Received empty response from Gemini model."
        
        return analysis
    
    except requests.exceptions.Timeout:
        return "Error: Request to OpenRouter timed out."
    except requests.exceptions.HTTPError as e:
        error_detail = f"HTTP Error {e.response.status_code}"
        try:
            error_content = response.json().get('error', {})
            error_detail = f"API Error {error_content.get('code', e.response.status_code)}: {error_content.get('message', 'No details provided')}"
        except (json.JSONDecodeError, AttributeError):
            error_detail = f"HTTP Error {e.response.status_code}: {response.text[:200]}"
        return f"Error: {error_detail}"
    except requests.exceptions.RequestException as e:
        return f"Error: Network error occurred: {e}"
    except Exception as e:
        return f"Error: Unexpected error occurred: {e}"

# --- Streamlit App UI ---
st.set_page_config(page_title="Detailed PSI Accessibility Checker", layout="wide")
st.title("📊 Detailed PageSpeed Insights Accessibility Checker")
st.markdown("""
Upload a CSV file with a column named **'urls'**. The app fetches the overall **WCAG 2.0 AA Accessibility Score**
and provides details on specific audits that require attention for each URL using the Google PageSpeed Insights API.
""")

# --- Important Considerations Expander ---
with st.expander("⚠️ Important Considerations & How to Interpret Results"):
    st.markdown(f"""
    *   **API Limits:** Google enforces [rate limits](https://developers.google.com/speed/docs/insights/v5/reference/limits). Large lists might hit these. The app uses a `{API_CALL_DELAY}s` delay.
    *   **Automated != Fully Compliant:** This tool uses Lighthouse for *automated* checks based on WCAG principles. It's a great starting point but **cannot guarantee full WCAG 2.0 AA compliance**. Manual testing (especially with screen readers and diverse users) is essential.
    *   **Understanding Audit Categories:**
        * **Failed Audits ❌** - These are accessibility issues automatically detected that must be fixed to improve accessibility. They violate WCAG guidelines and affect users with disabilities.
        * **Requires Manual Verification ⚠️** - Automated tools cannot fully verify these aspects. They require human judgment and testing with assistive technologies like screen readers.
        * **Passed Audits ✅** - These accessibility requirements have been successfully met according to automated testing. While this is positive, remember that automated testing only covers about 30% of potential accessibility issues.
        * **Not Applicable ⏩** - These audits don't apply to the current page, often because the page doesn't contain the relevant elements (e.g., video audits when no videos are present).
    *   **WCAG Basis:** Lighthouse audits are designed to test for failures of WCAG success criteria. While the report shows specific technical checks (e.g., 'image-alt', 'link-name'), these directly relate to WCAG principles like Perceivable, Operable, Understandable, Robust. The audit descriptions often provide context.
    *   **Other Factors:** Remember URL accessibility (no logins), dynamic content behaviour, and potential timeouts ({REQUEST_TIMEOUT}s).
    """)

# 1. Check for API Key (Same as before)
api_key = os.getenv("PAGESPEED_API_KEY")
if not api_key:
    st.error("🛑 **Error:** `PAGESPEED_API_KEY` environment variable not found.")
    st.stop()
else:
    masked_key = api_key[:4] + "****" + api_key[-4:]
    st.success(f"✅ API Key found (ends in ...{masked_key[-8:]}).")
# Check for OpenRouter API Key
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
if not openrouter_api_key:
    st.warning("⚠️ **Warning:** `OPENROUTER_API_KEY` environment variable not found. Gemini AI analysis will not be available.")
else:
    masked_openrouter_key = openrouter_api_key[:4] + "****" + openrouter_api_key[-4:]
    st.success(f"✅ OpenRouter API Key found (ends in ...{masked_openrouter_key[-8:]}).")


# 2. Analysis Strategy Information
st.info("The app will analyze URLs using both **desktop** and **mobile** strategies for comprehensive accessibility testing.")

# --- Session State Initialization ---
# Use session state to store results across reruns (e.g., when selecting a URL for details)
if 'results_df' not in st.session_state:
    st.session_state.results_df = None
if 'detailed_results' not in st.session_state:
    st.session_state.detailed_results = {} # Store detailed audits keyed by original index
if 'gemini_analyses' not in st.session_state:
    st.session_state.gemini_analyses = {} # Store Gemini analyses keyed by URL
if 'last_uploaded_filename' not in st.session_state:
    st.session_state.last_uploaded_filename = None


# 3. File Uploader & Processing Logic
uploaded_file = st.file_uploader("📂 Choose your CSV file (must contain 'urls' column)", type="csv")

# Check if a new file has been uploaded or if it's the same file
process_file = False
if uploaded_file is not None:
    if uploaded_file.name != st.session_state.get('last_uploaded_filename'):
        process_file = True
        # Clear previous results when a new file is uploaded
        st.session_state.results_df = None
        st.session_state.detailed_results = {}
        st.session_state.gemini_analyses = {}
        st.session_state.last_uploaded_filename = uploaded_file.name
    elif st.session_state.results_df is None:
        # If the same file is uploaded again, but results were cleared, process again
        process_file = True


if process_file:
    try:
        df = pd.read_csv(uploaded_file)
        if 'urls' not in df.columns:
            st.error("❌ **Error:** The CSV file must contain a column named exactly 'urls'.")
            st.stop()

        df = df[['urls']].copy().dropna(subset=['urls'])
        df = df[df['urls'].astype(str).str.strip() != '']
        df.reset_index(drop=True, inplace=True) # Ensure index is sequential 0, 1, 2...

        if df.empty:
            st.warning("⚠️ No valid URLs found in the uploaded file after cleaning.")
            st.stop()

        st.write(f"Found {len(df)} URLs to process using both desktop and mobile strategies...")

        desktop_scores = []
        mobile_scores = []
        st.session_state.detailed_results = {} # Reset details for new run
        st.session_state.desktop_results = {}
        st.session_state.mobile_results = {}
        progress_bar = st.progress(0)
        status_text = st.empty()
        total_urls = len(df) * 2  # Each URL is processed twice (desktop and mobile)
        start_time = time.time()
        
        # Process counter for progress calculation
        process_count = 0

        for i, row in df.iterrows(): # Use iterrows to get index `i` easily
            url = row['urls']
            
            # Process desktop strategy
            process_count += 1
            current_progress = process_count / total_urls
            elapsed_time = time.time() - start_time
            avg_time_per_process = elapsed_time / process_count if process_count > 0 else elapsed_time
            estimated_remaining = (total_urls - process_count) * avg_time_per_process if avg_time_per_process > 0 else 0

            status_text.text(
                f"⚙️ Processing URL {i+1}/{len(df)} (Desktop): {url}\n"
                f"⏳ Estimated time remaining: {time.strftime('%M:%S', time.gmtime(estimated_remaining))}"
            )

            # Call the API function for desktop
            desktop_result = get_psi_accessibility_details(url, api_key, 'desktop')

            if "error" in desktop_result:
                desktop_scores.append(desktop_result["error"])
                st.session_state.desktop_results[i] = [{"error": desktop_result["error"]}]
            else:
                desktop_scores.append(desktop_result['score'])
                st.session_state.desktop_results[i] = desktop_result['audits']

            progress_bar.progress(current_progress)
            time.sleep(API_CALL_DELAY)
            
            # Process mobile strategy
            process_count += 1
            current_progress = process_count / total_urls
            elapsed_time = time.time() - start_time
            avg_time_per_process = elapsed_time / process_count if process_count > 0 else elapsed_time
            estimated_remaining = (total_urls - process_count) * avg_time_per_process if avg_time_per_process > 0 else 0

            status_text.text(
                f"⚙️ Processing URL {i+1}/{len(df)} (Mobile): {url}\n"
                f"⏳ Estimated time remaining: {time.strftime('%M:%S', time.gmtime(estimated_remaining))}"
            )

            # Call the API function for mobile
            mobile_result = get_psi_accessibility_details(url, api_key, 'mobile')

            if "error" in mobile_result:
                mobile_scores.append(mobile_result["error"])
                st.session_state.mobile_results[i] = [{"error": mobile_result["error"]}]
            else:
                mobile_scores.append(mobile_result['score'])
                st.session_state.mobile_results[i] = mobile_result['audits']

            progress_bar.progress(current_progress)
            time.sleep(API_CALL_DELAY)

        end_time = time.time()
        total_time = end_time - start_time
        status_text.success(f"✅ Processing complete for {len(df)} URLs (desktop and mobile) in {time.strftime('%M minutes %S seconds', time.gmtime(total_time))}!")

        # Store results in session state DataFrame
        df['Desktop Score'] = desktop_scores
        df['Mobile Score'] = mobile_scores
        st.session_state.results_df = df # Save the DataFrame to session state


    except pd.errors.EmptyDataError:
        st.error("❌ **Error:** The uploaded CSV file appears to be empty.")
        st.session_state.results_df = None # Clear results on error
        st.session_state.detailed_results = {}
        st.session_state.gemini_analyses = {}
    except Exception as e:
        st.error(f"An unexpected error occurred while processing the file: {e}")
        st.exception(e)
        st.session_state.results_df = None # Clear results on error
        st.session_state.detailed_results = {}
        st.session_state.gemini_analyses = {}

# --- Display Results ---
if st.session_state.results_df is not None:
    # st.subheader("📊 Summary Results")
    # st.dataframe(st.session_state.results_df, use_container_width=True)

    # --- Detailed View Section ---
    st.subheader("🔍 Detailed Audit Report")
    st.markdown("Select a URL from the list above to view its detailed accessibility audit results.")

    # Create options for the select box: "Index: URL"
    url_options = [f"{idx}: {url}" for idx, url in st.session_state.results_df['urls'].items()]

    if not url_options:
        st.warning("No URLs were processed successfully to show details for.")
    else:
        selected_option = st.selectbox("Choose URL to inspect:", options=url_options, index=0) # Default to first URL

        if selected_option:
            # Extract the index from the selected option string
            selected_index = int(selected_option.split(":")[0])
            current_url = st.session_state.results_df.loc[selected_index, 'urls']
            
            st.markdown(f"**Details for:** `{current_url}`")
            
            # Create tabs for desktop and mobile results
            desktop_tab, mobile_tab = st.tabs(["💻 Desktop Results", "📱 Mobile Results"])
            
            # Function to display audit results for a specific device type
            def display_audit_results(device_type, audits_to_display):
                if not audits_to_display:
                    st.info(f"No accessibility audits were found for this URL on {device_type}, or an error occurred during its analysis.")
                    return
                
                if "error" in audits_to_display[0]: # Check if the stored detail is an error message
                    st.error(f"Could not retrieve details due to a previous error: {audits_to_display[0]['error']}")
                    return
                
                # Group audits by category
                failed_audits = [a for a in audits_to_display if a.get('category') == 'failed']
                manual_audits = [a for a in audits_to_display if a.get('category') == 'manual_check']
                passed_audits = [a for a in audits_to_display if a.get('category') == 'passed']
                na_audits = [a for a in audits_to_display if a.get('category') == 'not_applicable']
                
                # Create summary data for visualization
                categories = ["Failed", "Manual Check", "Passed", "Not Applicable"]
                counts = [len(failed_audits), len(manual_audits), len(passed_audits), len(na_audits)]
                
                # Display summary statistics
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.subheader(f"{device_type} Audit Summary")
                    summary_df = pd.DataFrame({
                        "Category": categories,
                        "Count": counts
                    })
                    
                    # Create a horizontal bar chart
                    chart = st_alt.Chart(summary_df).mark_bar().encode(
                        x='Count:Q',
                        y=st_alt.Y('Category:N', sort=None),
                        color=st_alt.Color('Category:N', scale=st_alt.Scale(
                            domain=categories,
                            range=['#ff4b4b', '#ffa500', '#00cc44', '#aaaaaa']
                        ))
                    ).properties(
                        title=f'{device_type} Accessibility Audit Distribution'
                    )
                    st.altair_chart(chart, use_container_width=True)
                
                with col2:
                    st.subheader("Statistics")
                    total_audits = sum(counts)
                    if total_audits > 0:
                        st.metric("Total Audits", total_audits)
                        st.metric("Automated Pass Rate", f"{int((len(passed_audits) / total_audits) * 100)}%")
                        st.metric("Issues to Fix", len(failed_audits))
                        st.metric("Manual Checks Needed", len(manual_audits))
                
                # Display manual testing guidance
                manual_testing_tips = {
                    'keyboard-navigation': "Test by navigating the entire page using only Tab, Shift+Tab, Enter, and arrow keys.",
                    'logical-tab-order': "Verify that tabbing through the page follows a logical sequence matching visual layout.",
                    'focus-traps': "Check that keyboard focus isn't trapped in any component without a way to exit.",
                    'color-contrast': "Verify text is readable against its background for users with low vision or color blindness.",
                    'document-title': "Ensure the page title accurately describes the page content for screen reader users.",
                    'aria-allowed-attr': "Test with screen readers to ensure ARIA attributes convey the correct information.",
                    'aria-hidden-body': "Verify that screen readers can access the page content.",
                    'aria-hidden-focus': "Check that no focusable elements are within aria-hidden elements.",
                    'aria-input-field-name': "Test with screen readers to ensure input fields are properly labeled.",
                    'aria-toggle-field-name': "Verify toggle controls have accessible names that describe their purpose.",
                    'form-field-multiple-labels': "Check that form fields don't have conflicting labels that confuse screen readers.",
                    'heading-order': "Verify headings follow a logical hierarchical structure (h1, then h2, etc.).",
                    'duplicate-id-aria': "Check that ARIA references point to the correct unique elements.",
                    'meta-viewport': "Test zooming and scaling on mobile devices to ensure content remains accessible."
                }
                
                # Use expanders for better organization
                if failed_audits:
                    with st.expander("❌ Failed Audits", expanded=True):
                        st.markdown("These are accessibility issues automatically detected that must be fixed:")
                        for audit in failed_audits:
                            with st.container():
                                st.markdown("---")
                                st.warning(f"**{audit.get('title')}** (ID: `{audit.get('id')}`)")
                                st.markdown(f"> {audit.get('description')}")
                                if audit.get('details_snippet') and audit.get('details_snippet') != " (No specific item snippet)":
                                    st.code(f"Example Snippet:\n{audit.get('details_snippet')}", language='html')
                
                # Gemini AI Analysis Section
                if failed_audits:
                    with st.expander("🤖 AI Analysis with Gemini", expanded=True):
                        analysis_key = f"{current_url}_{device_type.lower()}"
                        
                        if analysis_key in st.session_state.gemini_analyses:
                            st.markdown("### Gemini's Recommendations")
                            st.markdown(st.session_state.gemini_analyses[analysis_key])
                        else:
                            if st.button(f"Analyze {device_type} Issues with Gemini", key=f"gemini_{device_type.lower()}"):
                                with st.spinner("Sending to Gemini for analysis..."):
                                    analysis = get_gemini_analysis(failed_audits, f"{current_url} ({device_type})")
                                    
                                    # Store the analysis in session state
                                    st.session_state.gemini_analyses[analysis_key] = analysis
                                    
                                    # Update the results DataFrame to include the analysis
                                    column_name = f'Gemini Analysis ({device_type})'
                                    if column_name not in st.session_state.results_df.columns:
                                        st.session_state.results_df[column_name] = ""
                                    
                                    st.session_state.results_df.loc[selected_index, column_name] = analysis
                                    
                                    # Display the analysis
                                    st.markdown("### Gemini's Recommendations")
                                    st.markdown(analysis)
                                    
                                    # Rerun to update the UI
                                    st.rerun()
                
                # Manual Verification Section
                if manual_audits:
                    with st.expander("⚠️ Requires Manual Verification", expanded=False):
                        st.markdown("These audits cannot be automatically verified and require human testing:")
                        for audit in manual_audits:
                            with st.container():
                                st.markdown("---")
                                st.info(f"**{audit.get('title')}** (ID: `{audit.get('id')}`) - {audit.get('displayMode')}")
                                st.markdown(f"> {audit.get('description')}")
                                
                                # Add testing guidance if available
                                if audit.get('id') in manual_testing_tips:
                                    st.markdown(f"**How to test:** {manual_testing_tips[audit.get('id')]}")
                                    
                                if audit.get('details_snippet') and audit.get('details_snippet') != " (No specific item snippet)":
                                    st.code(f"Example Snippet:\n{audit.get('details_snippet')}", language='html')
                
                # Passed Audits Section
                if passed_audits:
                    with st.expander("✅ Passed Audits", expanded=False):
                        st.markdown("These accessibility requirements have been successfully met according to automated testing:")
                        for audit in passed_audits:
                            st.markdown(f"- **{audit.get('title')}** (ID: `{audit.get('id')}`)")
                
                # Not Applicable Section
                if na_audits:
                    with st.expander("⏩ Not Applicable Audits", expanded=False):
                        st.markdown("These audits don't apply to the current page, often because the page doesn't contain the relevant elements:")
                        for audit in na_audits:
                            st.markdown(f"- **{audit.get('title')}** (ID: `{audit.get('id')}`)")
            
            # Display desktop results
            with desktop_tab:
                desktop_audits = st.session_state.desktop_results.get(selected_index, [])
                display_audit_results("Desktop", desktop_audits)
            
            # Display mobile results
            with mobile_tab:
                mobile_audits = st.session_state.mobile_results.get(selected_index, [])
                display_audit_results("Mobile", mobile_audits)

    # --- Download Button (using session state df) ---
    @st.cache_data # Cache the conversion
    def convert_df_to_csv(df_to_convert):
        # Ensure the Gemini Analysis columns exist
        if 'Gemini Analysis (Desktop)' not in df_to_convert.columns:
            df_to_convert['Gemini Analysis (Desktop)'] = ""
        if 'Gemini Analysis (Mobile)' not in df_to_convert.columns:
            df_to_convert['Gemini Analysis (Mobile)'] = ""
        
        return df_to_convert.to_csv(index=False).encode('utf-8')

    csv_output = convert_df_to_csv(st.session_state.results_df)

    st.download_button(
        label="💾 Download Complete Analysis as CSV",
        data=csv_output,
        file_name='pagespeed_accessibility_summary_complete.csv',
        mime='text/csv',
    )

elif not uploaded_file:
    st.info("Awaiting CSV file upload to begin analysis.")