import ast
import astor
import json
import os
import anthropic
import importlib.util
import inspect
from typing import Dict, Any, Tuple, Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

# System prompts as constants
SYSTEM_PROMPT_INNER = """
You are an expert software engineer.
You are given a function and a description of the function.
You need to return the function with the description of the function.
you ned to score the function with a score of 1-100.
Return your response in the following format:
{
    "Code": "function code",
    "Description": "description of the function",
    "Score": "score of the improved function (1-100)"
}
Ensure your response contains only valid JSON that can be parsed by Python's json.loads().
"""

SYSTEM_PROMPT_OUTER = """
You are an expert software engineer.
You are given A DICTIONARY of 3 functions and a description of the function.
You need to Rank the functions.
Return your the best function in the following format:
{
    "Code": "function code",
    "Description": "description of the function",
    "Score": "score of the improved function (1-100)"
}
Ensure your response contains only valid JSON that can be parsed by Python's json.loads().
"""


class CodeGenerated(BaseModel): #define the pydantic model for the code generated
    Code: str
    Description: str
    Score: int

class ChainPromptingPrac:
    def __init__(self):
        self.num_idea: int
        self.iteration: int
    
    def receiving_code_desc(self): #receive the code and description from the user
        while True:
            try:
                print("Welcome to the Code improver 5000!\n" 
                      "The code provided need to be Standalone Functionality and not a class\n"
                      "on top of that it needs description!")
                #recvieving python code name and function
                module_path = input("Please enter the module path (e.g., 'mymodule.py'): ")
                function_name = input("Please enter the function name and description should be (name)_description (without parameters): ")
                
                self.iteration = int(input("How many iteration you want: "))
                self.num_idea = int(input("How many ideas for each iteration you want: "))
                # Remove .py extension if present
                if module_path.endswith('.py'):
                    module_path = module_path[:-3]
                
                try:
                    #Locating code and creating a modul
                    spec = importlib.util.spec_from_file_location(module_path, f"{module_path}.py")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    # extracte specific function from code
                    code_received = getattr(module, function_name)
                    code_str = inspect.getsource(code_received)
                    # try get the description variable
                    try:
                        code_description = getattr(module, f"{function_name}_description")
                    except AttributeError:
                        code_description = str(input("Description varibale was not valid, write your description: "))
                    
                    if code_str and len(code_str) > 5:
                        print("Your function is valid")
                        break
                    print("Please provide a valid function")
                except (ImportError, AttributeError) as e:
                    print(f"Error loading function: {e}")
                    print("Please make sure the module path and function name are correct")
                    continue
                
            except Exception as e:
                print(f"Error: {e}")
                print("Please provide valid input")
        
        return code_str, code_description
    
    def extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]: #extract json from response
        try:
            # First try to parse the entire response as JSON (ideal case)
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If that fails, try to extract JSON using a more robust approach
            try:
                # Find the first { and last } for potential JSON content
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                #check if the json is valid
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = response_text[start_idx:end_idx]
                    return json.loads(json_str)
                else:
                    print("No valid JSON found in response")
                    return None
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON: {e}")
                print(f"Response text: {response_text}")
                return None
    
    def process_ai_response(self, response)-> Optional[Dict[str, Any]]: #process the ai response and extract the json data
        try:
            #extract the response content
            response_content = response.content[0].text if isinstance(response.content, list) else response.content
            response_content = str(response_content).strip()
            #extract the json from the response
            analysis = self.extract_json_from_response(response_content)
            #return the json data
            return {
                "Code": analysis["Code"],
                "Description": analysis["Description"],
                "Score": int(analysis.get("Score", analysis.get("Rank", 0)))
            }
        except Exception as e:
            print(f"Error processing AI response: {str(e)}")
            return None

    def brainstorming(self, code, code_description)->Dict[str, Dict[str, Any]]: #generate multiple ideas for code improvement
        try:
            print("Generating ideas...")
            #parse the code
            code_ast = ast.parse(code)
            #convert the code to a string
            code_str = astor.to_source(code_ast)
            #create a dictionary to store the ideas
            ideas_dict = {}
            #generate the ideas
            for i in range(self.num_idea):
                response = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    system=SYSTEM_PROMPT_INNER,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Please improve the following code by considering the following description: "},
                            {"type": "text", "text": f"Function: {code_str}"},
                            {"type": "text", "text": f"Description: {code_description}"}
                        ]
                    }],
                    max_tokens=2000
                )
                #process the ai response
                idea = self.process_ai_response(response)
                #check if the idea is valid
                if idea:
                    ideas_dict[f"Idea{i}"] = idea
                    
            return ideas_dict
        except Exception as e:
            print(f"Error in brainstorming: {str(e)}")
            return {}

    def brainstorming_loop(self, code, code_description): #loop through the iteration
        best_idea = None
        current_code = code
        current_description = code_description
        #loop through the iteration
        for iteration in range(self.iteration):
            print(f"beginning Iteration {iteration + 1} of {self.iteration}")
            #generate the ideas
            ideas_dict = self.brainstorming(current_code, current_description)
            #evaluate the ideas
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                system=SYSTEM_PROMPT_OUTER,
                messages=[{
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": f"Evaluate these function implementations and select the best one:\n{ideas_dict}"
                    }]
                }],
                max_tokens=2000
            )
            #process the ai response
            current_best = self.process_ai_response(response)
            #check if the best idea is valid
            if best_idea is None or current_best["Score"] > best_idea["Score"]:
                best_idea = current_best
            
            current_code = best_idea["Code"]
            current_description = best_idea["Description"]

            print(f"Iteration {iteration + 1} complete. Current best score: {best_idea['Score']}")
        
        #return the best idea
        return CodeGenerated(
            Code=best_idea['Code'],
            Description= best_idea['Description'],
            Score= best_idea['Score']
        )

def main():
    
    chain = ChainPromptingPrac()
    code, description=chain.receiving_code_desc()
    result = chain.brainstorming_loop(code, description)
    
    print("\nFinal best result:")
    print(f"Score: {result.Score}")
    print(f"Code:\n{result.Code}")
    print(f"Description: {result.Description}")

if __name__ == "__main__":
    main()