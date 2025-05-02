# PageSpeed Insights Accessibility Checker

A powerful Streamlit application that analyzes web pages for accessibility issues using Google's PageSpeed Insights API. This tool helps identify WCAG 2.0 AA compliance issues and provides detailed reports to improve web accessibility.


## 🌟 Features

- **Bulk URL Processing**: Upload a CSV file with multiple URLs for batch analysis
- **Comprehensive Accessibility Audits**: Based on Google Lighthouse and WCAG 2.0 AA guidelines
- **Detailed Reports**: View failed audits, manual checks needed, passed audits, and non-applicable tests
- **Visual Summaries**: Interactive charts showing audit distribution and statistics
- **Code Snippets**: See examples of problematic HTML for easier fixing
- **Manual Testing Guidance**: Tips for verifying issues that can't be automatically detected
- **Mobile & Desktop Analysis**: Choose which device type to simulate for testing
- **Export Results**: Download summary reports as CSV files

## 📋 Requirements

- Python 3.7+
- Google PageSpeed Insights API key
- Required Python packages:
  - streamlit
  - pandas
  - requests
  - altair

## 🚀 Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/pagespeed-accessibility-checker.git
   cd pagespeed-accessibility-checker
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your Google PageSpeed Insights API key:
   - Get an API key from [Google Cloud Console](https://console.cloud.google.com/)
   - Enable the PageSpeed Insights API
   - Set the environment variable:
     ```
     # On Windows
     set PAGESPEED_API_KEY=your_api_key_here
     
     # On macOS/Linux
     export PAGESPEED_API_KEY=your_api_key_here
     ```

## 💻 Usage

1. Start the Streamlit app:
   ```
   streamlit run psi_accessibility_app.py
   ```

2. Prepare a CSV file with a column named 'urls' containing the web pages you want to analyze

3. Upload your CSV file in the app interface

4. Select your preferred analysis strategy (mobile or desktop)

5. View the results and detailed reports for each URL

## 📊 Understanding the Results

The app categorizes accessibility audits into four groups:

- **Failed Audits ❌**: Automatically detected issues that must be fixed to improve accessibility
- **Requires Manual Verification ⚠️**: Aspects that need human judgment and testing with assistive technologies
- **Passed Audits ✅**: Requirements successfully met according to automated testing
- **Not Applicable ⏩**: Audits that don't apply to the current page

## ⚠️ Important Considerations

- **API Limits**: Google enforces rate limits on the PageSpeed Insights API
- **Automated ≠ Fully Compliant**: Automated testing covers only about 30% of potential accessibility issues
- **Manual Testing Required**: Complete accessibility assessment requires human testing with assistive technologies
- **WCAG Basis**: Lighthouse audits are designed to test for failures of WCAG success criteria

## 📝 License

[MIT License](LICENSE)

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/yourusername/pagespeed-accessibility-checker/issues).

## 📧 Contact

Project Link: [https://github.com/yourusername/pagespeed-accessibility-checker](https://github.com/yourusername/pagespeed-accessibility-checker)