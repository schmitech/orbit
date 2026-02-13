import React from 'react';
import { StyleSheet } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { ThemeColors } from '../theme/colors';

interface Props {
  content: string;
  theme: ThemeColors;
}

export function MarkdownContent({ content, theme }: Props) {
  const markdownStyles = StyleSheet.create({
    body: {
      color: theme.assistantBubbleText,
      fontSize: 16,
      lineHeight: 22,
    },
    paragraph: {
      marginTop: 0,
      marginBottom: 8,
    },
    heading1: {
      color: theme.assistantBubbleText,
      fontSize: 22,
      fontWeight: '700' as const,
      marginBottom: 8,
    },
    heading2: {
      color: theme.assistantBubbleText,
      fontSize: 20,
      fontWeight: '600' as const,
      marginBottom: 6,
    },
    heading3: {
      color: theme.assistantBubbleText,
      fontSize: 18,
      fontWeight: '600' as const,
      marginBottom: 4,
    },
    code_inline: {
      backgroundColor: theme.surfaceSecondary,
      color: theme.primary,
      paddingHorizontal: 5,
      paddingVertical: 2,
      borderRadius: 4,
      fontSize: 14,
      fontFamily: 'Menlo',
    },
    fence: {
      backgroundColor: theme.surfaceSecondary,
      padding: 12,
      borderRadius: 8,
      fontSize: 13,
      fontFamily: 'Menlo',
      color: theme.assistantBubbleText,
      marginVertical: 8,
    },
    code_block: {
      backgroundColor: theme.surfaceSecondary,
      padding: 12,
      borderRadius: 8,
      fontSize: 13,
      fontFamily: 'Menlo',
      color: theme.assistantBubbleText,
    },
    link: {
      color: theme.primary,
    },
    blockquote: {
      backgroundColor: theme.surfaceSecondary,
      borderLeftColor: theme.primary,
      borderLeftWidth: 3,
      paddingLeft: 12,
      paddingVertical: 4,
      marginVertical: 8,
    },
    bullet_list_icon: {
      color: theme.assistantBubbleText,
    },
    ordered_list_icon: {
      color: theme.assistantBubbleText,
    },
    list_item: {
      marginVertical: 2,
    },
    hr: {
      backgroundColor: theme.border,
      height: 1,
      marginVertical: 12,
    },
    table: {
      borderColor: theme.border,
    },
    th: {
      borderColor: theme.border,
      padding: 6,
    },
    td: {
      borderColor: theme.border,
      padding: 6,
    },
    strong: {
      fontWeight: '700' as const,
    },
  });

  return <Markdown style={markdownStyles}>{content}</Markdown>;
}
