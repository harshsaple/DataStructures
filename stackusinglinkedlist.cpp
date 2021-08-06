#include<stdio.h>
#include<iostream>
using namespace std;

class Node{
    public:
    int data;
    Node* next;

};

void printList(Node* n){
    while(n!=NULL){
        cout<<n->data<<"";
        n=n->next;
    }
}

void push(Node **head_ref , int new_data)
{
    Node * new_node = new Node();

    new_node->data=new_data;
    new_node->next=*head_ref;
    *head_ref = new_node;
}

void pop(Node **head_ref )
{
    int position =0;
    if(*head_ref == NULL)
    return;
    
    Node *temp = *head_ref;

    if(position == 0){
        *head_ref = temp->next;
        free(temp);
        return;
    }   
}

int main()
{

    Node *first = NULL;
    Node *second = NULL;

    first = new Node();
    second = new Node();


    first->data =1;
    first->next = second;

    second->data=2;
    second->next=NULL;

    push(&first , 1);
    push(&first,2);
    push(&first,3);

    pop(&first);



    printList(first);



}