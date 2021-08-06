//Algorithm first
/*  Stack is LIFO 
Overflow if stack completely full and inderflow is stack completely empty
Applications : - reverse a word , expression conversion

Algo for push - stack:
check if stack is full ,
if full overflow else
increment top and insert element

Algo for pop
check if stack - empty - underflow
if not empty, pop the elee=ment ifrst and decrement the stack*/

#include<stdio.h>
#include<iostream>
using namespace std;

class Stack{

    public:
    int top;
    int stackarr[10];
    Stack()
    {
        top = -1;   
    }

    void push(int x);
    int pop();
    bool isEmpty();
    int peek();

};

void Stack::push(int x)
{
    if(top>=10)
    {
        cout<<"Stack OverFlow";
    }
    else{
        stackarr[++top] = x;
        cout << "Element inserted successfully"<<endl;
    }
}

int Stack::pop()
{
    if (top<0)
    {
        cout<<"Stack Underflow";
    }
    else
    {
        int x = stackarr[top--];
        cout<<"element popped is  "<<x<<endl;
        return x;


    }
}

bool Stack::isEmpty()
{
    if (top<0){
        return true;
    }
    else
    {
        return false;
    }
}

int Stack::peek()
{
    if (top < 0)
    {
        cout<<"stack is empty";
    }
    else{
        int y = stackarr[top];
    }
}

int main()
{
    class Stack s; // creating a object s of Class Stack;

    s.push(10);
    s.push(20);
    s.push(100);
    s.push(15);
    s.pop();
    s.pop();

    while(!s.isEmpty())
    {
        cout<<s.peek()<<endl;
        s.pop();
    }


}

