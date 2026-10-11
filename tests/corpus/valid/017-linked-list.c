#include <stdio.h>
#include <stdlib.h>

struct Node {
    int value;
    struct Node *next;
};

struct Node *push(struct Node *head, int value) {
    struct Node *node = (struct Node *)malloc(sizeof(struct Node));
    if (node == NULL) {
        return head;
    }
    node->value = value;
    node->next = head;
    return node;
}

int main(void) {
    struct Node *head = NULL;
    struct Node *cur;
    int i;
    for (i = 1; i <= 3; i++) {
        head = push(head, i * i);
    }
    for (cur = head; cur != NULL; cur = cur->next) {
        printf("%d ", cur->value);
    }
    printf("\n");
    while (head != NULL) {
        cur = head->next;
        free(head);
        head = cur;
    }
    return 0;
}
