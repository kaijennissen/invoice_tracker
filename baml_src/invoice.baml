// Defining a data model.
class InvoiceData {
  party string
  invoice_id string 
  issue_date string @description("ISO 8601 date format e.g., 2023-10-15")
  due_date string @description("ISO 8601 date format e.g., 2023-10-15")
  amount float 
  currency string
  recipient string
}

// Create a function to extract the resume from a string.
function ExtractInvoiceData(image: image) -> InvoiceData {
  // Specify a client as provider/model-name
  // You can also use custom LLM params with a custom client name from clients.baml like "client CustomGPT5" or "client CustomSonnet4"
  client CustomOllama // Set OPENAI_API_KEY to use this client.
  prompt #"
    Extract invoice data from this image. Be precise with dates (YYYY-MM-DD format) and amounts (numeric only, no currency symbols). For multi-page documents, the total amount is typically on the last page.
    {{ image }}

    {{ ctx.output_format }}
  "#
}



// Test the function with a sample resume. Open the VSCode playground to run this.
test TestName {
  functions [ExtractInvoiceData]
  args {
    image { file "/Users/kj/01_Projects/invoice_tracker/invoice.jpeg" }
  }
}